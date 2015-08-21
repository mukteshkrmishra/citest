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


from ..base.scribe import Scribable


class OperationContract(Scribable):
  @property
  def title(self):
    return self._operation.title

  @property
  def operation(self):
    return self._operation

  @property
  def contract(self):
    return self._contract

  def _make_scribe_parts(self, scribe):
    return [scribe.part_builder.build_nested_part(
               'Operation', self._operation),
            scribe.part_builder.build_nested_part('Contract', self._contract)]

  def __init__(self, operation, contract):
    """Construct instance.

    Args:
      operation: service_testing.AgentOperation to be performed.
      contract: json_contract.JsonContract to verify operation.
    """
    self._operation = operation
    self._contract = contract
