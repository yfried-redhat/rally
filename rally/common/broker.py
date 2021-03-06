# Copyright 2014: Mirantis Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import collections
import threading
import time

from rally.common.i18n import _
from rally.common import log as logging


LOG = logging.getLogger(__name__)


def _consumer(consume, queue, is_published):
    """Infinity worker that consumes tasks from queue.

    This finishes it's work only in case if is_published.isSet().

    :param consume: method that consumes an object removed from the queue
    :param queue: deque object to popleft() objects from
    :param is_published: threading.Event that is used to stop the consumer
                         when the queue is empty
    """
    cache = {}
    while True:
        if queue:
            try:
                consume(cache, queue.popleft())
            except IndexError:
                # NOTE(boris-42): queue is accessed from multiple threads so
                #                 it's quite possible to have 2 queue accessing
                #                 at the same point queue with only 1 element
                pass
            except Exception as e:
                LOG.warning(_("Failed to consume a task from the queue: "
                              "%s") % e)
                if logging.is_debug():
                    LOG.exception(e)
        elif is_published.isSet():
            break
        else:
            time.sleep(0.1)


def _publisher(publish, queue, is_published):
    """Calls a publish method that fills queue with jobs.

    After running publish method it sets is_published variable, that is used to
    stop workers (consumers).

    :param publish: method that fills the queue
    :param queue: deque object to be filled by the publish() method
    :param is_published: threading.Event that is used to stop consumers and
                         finish task
    """
    try:
        publish(queue)
    except Exception as e:
        LOG.warning(_("Failed to publish a task to the queue: %s") % e)
        if logging.is_debug():
            LOG.exception(e)
    finally:
        is_published.set()


def run(publish, consume, consumers_count=1):
    """Run broker.

    publish() put to queue, consume() process one element from queue.

    When publish() is finished and elements from queue are processed process
    is finished all consumers threads are cleaned.

    :param publish: Function that puts values to the queue
    :param consume: Function that processes a single value from the queue
    :param consumers_count: Number of consumers
    """
    queue = collections.deque()
    is_published = threading.Event()

    consumers = []
    for i in range(consumers_count):
        consumer = threading.Thread(target=_consumer,
                                    args=(consume, queue, is_published))
        consumer.start()
        consumers.append(consumer)

    _publisher(publish, queue, is_published)
    for consumer in consumers:
        consumer.join()
