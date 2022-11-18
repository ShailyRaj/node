#!/usr/bin/env python3
# Copyright 2020 the V8 project authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import heapq
import logging
import os
import platform
import re
import signal
import subprocess

# Base dir of the build products for Release and Debug.
OUT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'out'))


def list_processes_linux():
  """Returns list of tuples (pid, command) of processes running in the same out
  directory as this checkout.
  """
  if platform.system() != 'Linux':
    return []
  try:
    cmd = 'pgrep -fa %s' % OUT_DIR
    output = subprocess.check_output(cmd, shell=True, text=True) or ''
    processes = [
      (int(line.split()[0]), line[line.index(OUT_DIR):])
      for line in output.splitlines()
    ]
    # Filter strange process with name as out dir.
    return [p for p in processes if p[1] != OUT_DIR]
  except subprocess.CalledProcessError as e:
    # Return code 1 means no processes found.
    if e.returncode != 1:
      # TODO(https://crbug.com/v8/13101): Remove after investigation.
      logging.exception('Fetching process list failed.')
    return []


def kill_processes_linux():
  """Kill stray processes on the system that started in the same out directory.

  All swarming tasks share the same out directory location.
  """
  if platform.system() != 'Linux':
    return
  for pid, cmd in list_processes_linux():
    try:
      logging.warning('Attempting to kill %d - %s', pid, cmd)
      os.kill(pid, signal.SIGKILL)
    except:
      logging.exception('Failed to kill process')


def strip_ascii_control_characters(unicode_string):
  return re.sub(r'[^\x20-\x7E]', '?', str(unicode_string))


def base_test_record(test, result, run):
  record = {
      'name': test.full_name,
      'flags': result.cmd.args,
      'run': run + 1,
      'expected': test.expected_outcomes,
      'random_seed': test.random_seed,
      'target_name': test.get_shell(),
      'variant': test.variant,
      'variant_flags': test.variant_flags,
  }
  if result.output:
    record.update(
        exit_code=result.output.exit_code,
        duration=result.output.duration,
    )
  return record


def extract_tags(record):
  tags = []
  for k, v in record.items():
    if type(v) == list:
      tags += [sanitized_kv_dict(k, e) for e in v]
    else:
      tags.append(sanitized_kv_dict(k, v))
  return tags


def sanitized_kv_dict(k, v):
  return dict(key=k, value=strip_ascii_control_characters(v))


class FixedSizeTopList():
  """Utility collection for gathering a fixed number of elements with the
  biggest value for the given key. It employs a heap from which we pop the
  smallest element when the collection is 'full'.

  If you need a reversed behaviour (collect min values) just provide an
  inverse key."""

  def __init__(self, size, key=None):
    self.size = size
    self.key = key or (lambda x: x)
    self.data = []
    self.discriminator = 0

  def add(self, elem):
    elem_k = self.key(elem)
    heapq.heappush(self.data, (elem_k, self.extra_key(), elem))
    if len(self.data) > self.size:
      heapq.heappop(self.data)

  def extra_key(self):
    # Avoid key clash in tuples sent to the heap.
    # We want to avoid comparisons on the last element of the tuple
    # since those elements might not be comparable.
    self.discriminator += 1
    return self.discriminator

  def as_list(self):
    original_data = [rec for (_, _, rec) in self.data]
    return sorted(original_data, key=self.key, reverse=True)
