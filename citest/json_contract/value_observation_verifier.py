# Copyright 2015 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging

from . import binary_predicate
from . import cardinality_predicate
from . import logic_predicate
from . import map_predicate
from . import observation_verifier as ov
from . import observation_failure as of
from . import path_predicate
from . import predicate


class ValueObservationVerifierBuilder(ov.ObservationVerifierBuilder):
  def __init__(self, title, strict=False):
    super(ValueObservationVerifierBuilder, self).__init__(title)
    self.__strict = strict
    self.__constraints = []

  def __eq__(self, builder):
    return (super(ValueObservationVerifierBuilder, self).__eq__(builder)
            and self.__strict == builder.__strict
            and self.__constraints == builder.__constraints)

  def _do_build_generate(self, dnf_verifiers):
      return ValueObservationVerifier(
          title=self.title,
          dnf_verifiers=dnf_verifiers,
          unmapped_constraints=self.__constraints,
          strict=self.__strict)

  def export_to_json_snapshot(self, snapshot, entity):
    """Implements JsonSnapshotable interface."""
    snapshot.edge_builder.make_control(entity, 'Strict', self.__strict)
    if len(self.__constraints) == 1:
      # Optimize model for single-element list
      snapshot.edge_builder.make_control(
        entity, 'Constraint', self.__constraints[0])
    else:
      snapshot.edge_builder.make_control(
        entity, 'Constraints', self.__constraints)

    super(ValueObserverVerifierBuilder, self).export_to_json_snapshot(
        snapshot, entity)

  def add_constraint(self, constraint):
    if not isinstance(constraint, predicate.ValuePredicate):
      raise TypeError('{0} is not predicate.ValuePredicate'.format(
          constraint.__class__))
    self.__constraints.append(constraint)
    return self

  def add_mapped_constraint(self, constraint, min=1, max=None):
    pred = map_predicate.MapPredicate(pred=constraint, min=min, max=max)
    self.__constraints.append(
        map_predicate.MapPredicate(pred=constraint, min=min, max=max))
    return self

  def contains_path_value(self, path, value, min=1, max=None):
    return self.contains_path_pred(
        path, binary_predicate.CONTAINS(value), min, max)

  def contains_path_eq(self, path, value, min=1, max=None):
    return self.contains_path_pred(
        path, binary_predicate.EQUIVALENT(value), min, max)

  def contains_path_pred(self, path, pred, min=1, max=None):
    self.add_constraint(
      cardinality_predicate.CardinalityPredicate(
          path_predicate.PathPredicate(path, pred), min=min, max=max))
    return self

  def contains_pred_list(self, pred_list, min=1, max=None):
    conjunction = logic_predicate.AND(pred_list)
    self.add_constraint(
        cardinality_predicate.CardinalityPredicate(
            conjunction, min=min, max=max))
    return self

  def excludes_path_pred(self, path, pred, max=0):
    self.add_constraint(
        cardinality_predicate.CardinalityPredicate(
            path_predicate.PathPredicate(path, pred), min=0, max=max))
    return self

  def excludes_path_value(self, path, value, max=0):
    return self.excludes_path_pred(path, binary_predicate.CONTAINS(value), max)

  def excludes_path_eq(self, path, value, max=0):
    return self.excludes_path_pred(
        path, binary_predicate.EQUIVALENT(value), max)

  def excludes_pred_list(self, pred_list, max=0):
    conjunction = logic_predicate.AND(pred_list)
    self.add_constraint(
        cardinality_predicate.CardinalityPredicate(
            conjunction, min=0, max=max))
    return self


class ValueObservationVerifier(ov.ObservationVerifier):
  @property
  def constraints(self):
    return self.__constraints

  @property
  def strict(self):
    return self.__strict

  def export_to_json_snapshot(self, snapshot, entity):
    """Implements JsonSnapshotable interface."""
    snapshot.edge_builder.make_control(entity, 'Strict', self.__strict)
    snapshot.edge_builder.make_control(
        entity, 'Constraints', self.__constraints)
    super(ValueObservationVerifier, self).export_to_json_snapshot(
        snapshot, entity)

  def __str__(self):
    return '{0} constraints={1} strict={2}'.format(
        super(ValueObservationVerifier, self).__str__(),
        [str(x) for x in self.__constraints],
        self.__strict)

  def __init__(self,
               title, dnf_verifiers=None,
               mapped_constraints=None,
               unmapped_constraints=None,
               strict=False):
    """Construct instance.

    Args:
      title: The name of the verifier for reporting purposes only.
      dnf_verifiers: A list of lists of jc.ObservationVerifier where the outer
          list are OR'd together and the inner lists are AND'd together
          (i.e. disjunctive normal form).
      unmapped_constraints: A list of jc.ValuePredicate to apply to the
          observation object list.
      mapped_constraints: A list of jc.ValuePredicate to apply to the
          individual objects within the observation object list.
      strict: If True then the verifier requires all the observed elements to
          satisfy all the constraints (including future added constraints).
          Otherwise if False then the verifier requires each of the constraints
          to be satisfied by at least one object. Not necessarily the same
          object, nor does any object have to satisfy even one constraint.
    """
    super(ValueObservationVerifier, self).__init__(title, dnf_verifiers)
    self.__strict = strict
    self.__constraints = []
    if unmapped_constraints:
      self.__constraints.extend(unmapped_constraints)
    for c in mapped_constraints or []:
      self.__constraints.append(map_predicate.MapPredicate(c))

  def __call__(self, observation):
    if observation.errors:
      logging.getLogger(__name__).debug(
        'Failing because of observation errors %s', observation.errors)
      return ov.ObservationVerifyResult(
          valid=False, observation=observation,
          all_results=[of.ObservationFailedError(observation.errors)],
          good_results=[], bad_results=[], failed_constraints=[],
          comment='Observation Failed.')

    all_objects = observation.objects
    if not all_objects:
      # If we have no objects, then we will not iterate over anything
      # so will not check any contracts.
      # Instead, add a None object to the list so we'll check each contract
      # against None to see if it is satisfied.
      logging.getLogger(__name__).debug(
          'Verifying object None to indicate no objects at all.')
      object_list = [None]
    else:
      object_list = all_objects

    # Every constraint must be satisfied by at least one object.
    # If strict then every object must be verified by at least one constraint.
    valid = True
    final_builder = ov.ObservationVerifyResultBuilder(observation)

    for constraint in self.__constraints:
      logging.getLogger(__name__).debug('Verifying constraint=%s', constraint)
      constraint_result = constraint(object_list)

      if not constraint_result:
        logging.getLogger(__name__).debug('FAILED constraint')
        valid = False

      # This is messy. On one hand we may want to have mapped results
      # to show which objects are valid or not if we are looking individually.
      # But on the other hand, we might be looking at all the objects as a
      # collection in whole (e.g. cardinality). Really we should not be
      # assuming a map predicate result, but currently are. So we're going
      # to coerce non-map results into map results.
      # TODO(ewiseblatt): Fix this by refactoring this and its base class.
      skip_strict = True
      if isinstance(constraint_result, map_predicate.MapPredicateResult):
          # If we didnt map anything, then the strict check isnt appropriate.
          skip_strict = False
      else:
          map_result_builder = map_predicate.MapPredicateResultBuilder(
              constraint)
          map_result_builder.add_result([object_list], constraint_result)
          constraint_result = map_result_builder.build(constraint_result.valid)
          if constraint_result.valid:
            skip_strict = True
      final_builder.add_map_result(constraint_result)

    if valid and self.__strict and not skip_strict:
      len_validated = len(final_builder.validated_object_set)
      len_objects = len(object_list)
      valid = len_validated == len_objects

      if not valid:
        logging.getLogger(__name__).error(
          'Strict verifier "%s" only confirmed %d of %d objects.',
          self.title, len_validated, len_objects)

    return final_builder.build(valid)
