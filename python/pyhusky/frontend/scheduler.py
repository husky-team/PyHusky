# Copyright 2016 Husky Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import random
import time

from pyhusky.common.binstream import BinStream
from pyhusky.common.operation import Operation
from pyhusky.frontend import communication
from pyhusky.frontend import config
from pyhusky.frontend.datareceiver import data_receiver

id_counter = 0

def visit_deps(op, bs):
    """
    structure of binstream
    [node id][op][dep_id1, dep_id2, ...][node id][op][dep_id1, dep_id2, ...]
    """

    global id_counter
    id_counter += 1
    bid = id_counter

    self_dep_list = []
    for dep in op.op_deps:
        if dep.is_materialized:  # create a virtual node for cache
            dep = Operation("Functional#load_cache_py", dep.op_param, [])
        dep_id = visit_deps(dep, bs)
        self_dep_list.append(dep_id)

    bs << bid
    bs << op
    bs << self_dep_list
    config.log_msg(op)
    return bid


def serialize_dag(pending_op):
    global id_counter
    id_counter = -1
    bs = BinStream()
    visit_deps(pending_op, bs)
    bs << -1  # mark of end
    return bs


def submit_task(bin_dag, op):
    task_id = random.randint(0, 1000)
    bin_dag << task_id
    communication.send(communication.NEW_TASK, bin_dag.data_buf)
    result = None
    cur_prgs = -1
    while True:
        time.sleep(0.001)
        question = BinStream()
        question << task_id
        reply = BinStream()
        reply.data_buf = communication.ask(communication.QUERY_TASK, question.data_buf)
        status = reply.load_str()
        if status == "progress":
            prgs = reply.load_int32()
            if cur_prgs != prgs:
                cur_prgs = prgs
                config.log_msg("Executing... "+str(prgs)+" %")
            if prgs == 100:
                break
        elif status == "data":
            ret = data_receiver(reply, op)
            if ret is not None:
                if result is None:
                    result = ret
                else:
                    result += ret

    return result


def compute(op):
    bin_dag = serialize_dag(op)
    submit_task(bin_dag, op)


def compute_collect(op):
    bin_dag = serialize_dag(op)
    result = submit_task(bin_dag, op)
    return result
