# Copyright 2013: Mirantis Inc.
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

import copy
import datetime as date
import os.path

import mock

from rally.cmd.commands import task
from rally import consts
from rally import exceptions
from tests.unit import fakes
from tests.unit import test


class TaskCommandsTestCase(test.TestCase):

    def setUp(self):
        super(TaskCommandsTestCase, self).setUp()
        self.task = task.TaskCommands()

    @mock.patch("rally.cmd.commands.task.open", create=True)
    def test_load_task(self, mock_open):
        input_task = "{'ab': {{test}}}"
        input_args = "{'test': 2}"

        # NOTE(boris-42): Such order of files is because we are reading
        #                 file with args before file with template.
        mock_open.side_effect = [
            mock.mock_open(read_data="{'test': 1}").return_value,
            mock.mock_open(read_data=input_task).return_value
        ]
        result = self.task._load_task("in_task", task_args_file="in_args_path")
        self.assertEqual(result, {"ab": 1})

        mock_open.side_effect = [
            mock.mock_open(read_data=input_task).return_value
        ]
        result = self.task._load_task("in_task", task_args=input_args)
        self.assertEqual(result, {"ab": 2})

        mock_open.side_effect = [
            mock.mock_open(read_data="{'test': 1}").return_value,
            mock.mock_open(read_data=input_task).return_value

        ]
        result = self.task._load_task("in_task", task_args=input_args,
                                      task_args_file="any_file")
        self.assertEqual(result, {"ab": 2})

    @mock.patch("rally.cmd.commands.task.open", create=True)
    def test_load_task_wrong_task_args_file(self, mock_open):
        mock_open.side_effect = [
            mock.mock_open(read_data="{'test': {}").return_value
        ]
        self.assertRaises(task.FailedToLoadTask,
                          self.task._load_task,
                          "in_task", task_args_file="in_args_path")

    @mock.patch("rally.cmd.commands.task.open", create=True)
    def test_load_task_wrong_task_args_file_exception(self, mock_open):
        mock_open.side_effect = IOError
        self.assertRaises(IOError, self.task._load_task,
                          "in_task", task_args_file="in_args_path")

    def test_load_task_wrong_input_task_args(self):
        self.assertRaises(task.FailedToLoadTask,
                          self.task._load_task, "in_task", "{'test': {}")
        self.assertRaises(task.FailedToLoadTask,
                          self.task._load_task, "in_task", "[]")

    @mock.patch("rally.cmd.commands.task.open", create=True)
    def test_load_task_task_render_raise_exc(self, mock_open):
        mock_open.side_effect = [
            mock.mock_open(read_data="{'test': {{t}}}").return_value
        ]
        self.assertRaises(task.FailedToLoadTask,
                          self.task._load_task, "in_task")

    @mock.patch("rally.cmd.commands.task.open", create=True)
    def test_load_task_task_not_in_yaml(self, mock_open):
        mock_open.side_effect = [
            mock.mock_open(read_data="{'test': {}").return_value
        ]
        self.assertRaises(task.FailedToLoadTask,
                          self.task._load_task, "in_task")

    @mock.patch("rally.cmd.commands.task.TaskCommands.detailed")
    @mock.patch("rally.cmd.commands.task.TaskCommands._load_task",
                return_value={"some": "json"})
    @mock.patch("rally.api.Task.create")
    @mock.patch("rally.cmd.commands.task.api.Task.start")
    def test_start(self, mock_api, mock_create_task, mock_load,
                   mock_task_detailed):
        mock_create_task.return_value = (
            dict(uuid="c1a9bbe-1ead-4740-92b5-0feecf421634",
                 created_at="2014-01-14 09:14:45.395822",
                 status="init", tag=None))
        deployment_id = "e0617de9-77d1-4875-9b49-9d5789e29f20"
        task_path = "path_to_config.json"
        self.task.start(task_path, deployment_id)
        mock_api.assert_called_once_with(deployment_id, {"some": "json"},
                                         task=mock_create_task.return_value,
                                         abort_on_sla_failure=False)
        mock_load.assert_called_once_with(task_path, None, None)

    @mock.patch("rally.cmd.commands.task.TaskCommands._load_task",
                side_effect=task.FailedToLoadTask)
    def test_start_with_task_args(self, mock_load):
        task_path = mock.MagicMock()
        task_args = mock.MagicMock()
        task_args_file = mock.MagicMock()
        self.task.start(task_path, deployment="any", task_args=task_args,
                        task_args_file=task_args_file)
        mock_load.assert_called_once_with(task_path, task_args, task_args_file)

    @mock.patch("rally.cmd.commands.task.envutils.get_global")
    def test_start_no_deployment_id(self, mock_default):
        mock_default.side_effect = exceptions.InvalidArgumentsException
        self.assertRaises(exceptions.InvalidArgumentsException,
                          self.task.start, "path_to_config.json", None)

    @mock.patch("rally.cmd.commands.task.TaskCommands._load_task")
    @mock.patch("rally.cmd.commands.task.api")
    def test_start_invalid_task(self, mock_api, mock_load):
        mock_api.Task.start.side_effect = exceptions.InvalidConfigException

        result = self.task.start("task_path", "deployment", tag="tag")
        self.assertEqual(1, result)

        mock_api.Task.create.assert_called_once_with("deployment", "tag")
        mock_api.Task.start.assert_called_once_with(
            "deployment", mock_load.return_value,
            task=mock_api.Task.create.return_value, abort_on_sla_failure=False)

    @mock.patch("rally.cmd.commands.task.api")
    def test_abort(self, mock_api):
        test_uuid = "17860c43-2274-498d-8669-448eff7b073f"
        mock_api.Task.abort = mock.MagicMock()
        self.task.abort(test_uuid)
        task.api.Task.abort.assert_called_once_with(test_uuid)

    @mock.patch("rally.cmd.commands.task.envutils.get_global")
    def test_abort_no_task_id(self, mock_default):
        mock_default.side_effect = exceptions.InvalidArgumentsException
        self.assertRaises(exceptions.InvalidArgumentsException,
                          self.task.abort, None)

    def test_status(self):
        test_uuid = "a3e7cefb-bec2-4802-89f6-410cc31f71af"
        value = {"task_id": "task", "status": "status"}
        with mock.patch("rally.cmd.commands.task.db") as mock_db:
            mock_db.task_get = mock.MagicMock(return_value=value)
            self.task.status(test_uuid)
            mock_db.task_get.assert_called_once_with(test_uuid)

    @mock.patch("rally.cmd.commands.task.envutils.get_global")
    def test_status_no_task_id(self, mock_default):
        mock_default.side_effect = exceptions.InvalidArgumentsException
        self.assertRaises(exceptions.InvalidArgumentsException,
                          self.task.status, None)

    @mock.patch("rally.cmd.commands.task.db")
    def test_detailed(self, mock_db):
        test_uuid = "c0d874d4-7195-4fd5-8688-abe82bfad36f"
        value = {
            "id": "task",
            "uuid": test_uuid,
            "status": "status",
            "results": [
                {
                    "key": {
                        "name": "fake_name",
                        "pos": "fake_pos",
                        "kw": "fake_kw"
                    },
                    "data": {
                        "load_duration": 1.0,
                        "full_duration": 2.0,
                        "raw": [
                            {
                                "duration": 0.9,
                                "idle_duration": 0.5,
                                "scenario_output": {
                                    "data": {
                                        "a": 3
                                    },
                                    "errors": "some"
                                },
                                "atomic_actions": {
                                    "a": 0.6,
                                    "b": 0.7
                                },
                                "error": ["type", "message", "traceback"]
                            },
                            {
                                "duration": 0.5,
                                "idle_duration": 0.2,
                                "scenario_output": {
                                    "data": {
                                        "a": 1
                                    },
                                    "errors": "some"
                                },
                                "atomic_actions": {
                                    "a": 0.2,
                                    "b": 0.4
                                },
                                "error": None
                            },
                            {
                                "duration": 0.6,
                                "idle_duration": 0.4,
                                "scenario_output": {
                                    "data": {
                                        "a": 2
                                    },
                                    "errors": None
                                },
                                "atomic_actions": {
                                    "a": 0.3,
                                    "b": 0.5
                                },
                                "error": None
                            }
                        ]
                    }
                }
            ]
        }
        mock_db.task_get_detailed = mock.MagicMock(return_value=value)
        self.task.detailed(test_uuid)
        mock_db.task_get_detailed.assert_called_once_with(test_uuid)

        self.task.detailed(test_uuid, iterations_data=True)

    @mock.patch("rally.cmd.commands.task.db")
    @mock.patch("rally.cmd.commands.task.logging")
    def test_detailed_task_failed(self, mock_logging, mock_db):
        value = {
            "id": "task",
            "uuid": "task_uuid",
            "status": consts.TaskStatus.FAILED,
            "results": [],
            "verification_log": "['1', '2', '3']"
        }
        mock_db.task_get_detailed = mock.MagicMock(return_value=value)

        mock_logging.is_debug.return_value = False
        self.task.detailed("task_uuid")

        mock_logging.is_debug.return_value = True
        self.task.detailed("task_uuid")

    @mock.patch("rally.cmd.commands.task.envutils.get_global")
    def test_detailed_no_task_id(self, mock_default):
        mock_default.side_effect = exceptions.InvalidArgumentsException
        self.assertRaises(exceptions.InvalidArgumentsException,
                          self.task.detailed, None)

    @mock.patch("rally.cmd.commands.task.db")
    def test_detailed_wrong_id(self, mock_db):
        test_uuid = "eb290c30-38d8-4c8f-bbcc-fc8f74b004ae"
        mock_db.task_get_detailed = mock.MagicMock(return_value=None)
        self.task.detailed(test_uuid)
        mock_db.task_get_detailed.assert_called_once_with(test_uuid)

    @mock.patch("json.dumps")
    @mock.patch("rally.cmd.commands.task.objects.Task.get")
    def test_results(self, mock_get, mock_json):
        task_id = "foo_task_id"
        data = [
            {"key": "foo_key", "data": {"raw": "foo_raw", "sla": [],
                                        "load_duration": "lo_duration",
                                        "full_duration": "fu_duration"}}
        ]
        result = map(lambda x: {"key": x["key"],
                                "result": x["data"]["raw"],
                                "load_duration": x["data"]["load_duration"],
                                "full_duration": x["data"]["full_duration"],
                                "sla": x["data"]["sla"]}, data)
        mock_results = mock.Mock(return_value=data)
        mock_get.return_value = mock.Mock(get_results=mock_results)

        self.task.results(task_id)
        self.assertEqual(1, mock_json.call_count)
        self.assertEqual(1, len(mock_json.call_args[0]))
        self.assertSequenceEqual(result, mock_json.call_args[0][0])
        self.assertEqual({"sort_keys": True, "indent": 4},
                         mock_json.call_args[1])
        mock_get.assert_called_once_with(task_id)

    @mock.patch("rally.cmd.commands.task.objects.Task.get")
    def test_invalid_results(self, mock_get):
        task_id = "foo_task_id"
        data = []
        mock_results = mock.Mock(return_value=data)
        mock_get.return_value = mock.Mock(get_results=mock_results)

        result = self.task.results(task_id)
        mock_get.assert_called_once_with(task_id)
        self.assertEqual(1, result)

    @mock.patch("rally.cmd.commands.task.jsonschema.validate",
                return_value=None)
    @mock.patch("rally.cmd.commands.task.os.path.realpath",
                side_effect=lambda p: "realpath_%s" % p)
    @mock.patch("rally.cmd.commands.task.open",
                side_effect=mock.mock_open(), create=True)
    @mock.patch("rally.cmd.commands.task.plot")
    @mock.patch("rally.cmd.commands.task.webbrowser")
    @mock.patch("rally.cmd.commands.task.objects.Task.get")
    def test_report_one_uuid(self, mock_get, mock_web, mock_plot, mock_open,
                             mock_os, mock_validate):
        task_id = "eb290c30-38d8-4c8f-bbcc-fc8f74b004ae"
        data = [
            {"key": {"name": "test", "pos": 0},
             "data": {"raw": "foo_raw", "sla": "foo_sla",
                      "load_duration": 0.1,
                      "full_duration": 1.2}},
            {"key": {"name": "test", "pos": 0},
             "data": {"raw": "bar_raw", "sla": "bar_sla",
                      "load_duration": 2.1,
                      "full_duration": 2.2}}]

        results = [{"key": x["key"],
                    "result": x["data"]["raw"],
                    "sla": x["data"]["sla"],
                    "load_duration": x["data"]["load_duration"],
                    "full_duration": x["data"]["full_duration"]}
                   for x in data]
        mock_results = mock.Mock(return_value=data)
        mock_get.return_value = mock.Mock(get_results=mock_results)
        mock_plot.plot.return_value = "html_report"

        def reset_mocks():
            for m in mock_get, mock_web, mock_plot, mock_open:
                m.reset_mock()
        self.task.report(tasks=task_id, out="/tmp/%s.html" % task_id)
        mock_open.assert_called_once_with("/tmp/%s.html" % task_id, "w+")
        mock_plot.plot.assert_called_once_with(results)

        mock_open.side_effect().write.assert_called_once_with("html_report")
        mock_get.assert_called_once_with(task_id)

        reset_mocks()
        self.task.report(task_id, out="spam.html", open_it=True)
        mock_web.open_new_tab.assert_called_once_with(
            "file://realpath_spam.html")

    @mock.patch("rally.cmd.commands.task.jsonschema.validate",
                return_value=None)
    @mock.patch("rally.cmd.commands.task.os.path.realpath",
                side_effect=lambda p: "realpath_%s" % p)
    @mock.patch("rally.cmd.commands.task.open",
                side_effect=mock.mock_open(), create=True)
    @mock.patch("rally.cmd.commands.task.plot")
    @mock.patch("rally.cmd.commands.task.webbrowser")
    @mock.patch("rally.cmd.commands.task.objects.Task.get")
    def test_report_bunch_uuids(self, mock_get, mock_web, mock_plot, mock_open,
                                mock_os, mock_validate):
        tasks = ["eb290c30-38d8-4c8f-bbcc-fc8f74b004ae",
                 "eb290c30-38d8-4c8f-bbcc-fc8f74b004af"]
        data = [
            {"key": {"name": "test", "pos": 0},
             "data": {"raw": "foo_raw", "sla": "foo_sla",
                      "load_duration": 0.1,
                      "full_duration": 1.2}},
            {"key": {"name": "test", "pos": 0},
             "data": {"raw": "bar_raw", "sla": "bar_sla",
                      "load_duration": 2.1,
                      "full_duration": 2.2}}]

        results = list()
        for task_uuid in tasks:
            results.extend(
                map(lambda x: {"key": x["key"],
                               "result": x["data"]["raw"],
                               "sla": x["data"]["sla"],
                               "load_duration": x["data"]["load_duration"],
                               "full_duration": x["data"]["full_duration"]},
                    data))

        mock_results = mock.Mock(return_value=data)
        mock_get.return_value = mock.Mock(get_results=mock_results)
        mock_plot.plot.return_value = "html_report"

        def reset_mocks():
            for m in mock_get, mock_web, mock_plot, mock_open:
                m.reset_mock()
        self.task.report(tasks=tasks, out="/tmp/1_test.html")
        mock_open.assert_called_once_with("/tmp/1_test.html", "w+")
        mock_plot.plot.assert_called_once_with(results)

        mock_open.side_effect().write.assert_called_once_with("html_report")
        expected_get_calls = [mock.call(task) for task in tasks]
        mock_get.assert_has_calls(expected_get_calls, any_order=True)

    @mock.patch("rally.cmd.commands.task.json.load")
    @mock.patch("rally.cmd.commands.task.os.path.exists", return_value=True)
    @mock.patch("rally.cmd.commands.task.jsonschema.validate",
                return_value=None)
    @mock.patch("rally.cmd.commands.task.os.path.realpath",
                side_effect=lambda p: "realpath_%s" % p)
    @mock.patch("rally.cmd.commands.task.open", create=True)
    @mock.patch("rally.cmd.commands.task.plot")
    def test_report_one_file(self, mock_plot, mock_open, mock_os,
                             mock_validate, mock_path_exists, mock_json_load):

        task_file = "/tmp/some_file.json"
        data = [
            {"key": {"name": "test", "pos": 0},
             "data": {"raw": "foo_raw", "sla": "foo_sla",
                      "load_duration": 0.1,
                      "full_duration": 1.2}},
            {"key": {"name": "test", "pos": 1},
             "data": {"raw": "bar_raw", "sla": "bar_sla",
                      "load_duration": 2.1,
                      "full_duration": 2.2}}]

        results = [{"key": x["key"],
                    "result": x["data"]["raw"],
                    "sla": x["data"]["sla"],
                    "load_duration": x["data"]["load_duration"],
                    "full_duration": x["data"]["full_duration"]}
                   for x in data]

        mock_plot.plot.return_value = "html_report"
        mock_open.side_effect = mock.mock_open(read_data=results)

        mock_json_load.return_value = results

        def reset_mocks():
            for m in mock_plot, mock_open, mock_json_load, mock_validate:
                m.reset_mock()
        self.task.report(tasks=task_file, out="/tmp/1_test.html")
        expected_open_calls = [mock.call(task_file, "r"),
                               mock.call("/tmp/1_test.html", "w+")]
        mock_open.assert_has_calls(expected_open_calls, any_order=True)
        mock_plot.plot.assert_called_once_with(results)

        mock_open.side_effect().write.assert_called_once_with("html_report")

    @mock.patch("rally.cmd.commands.task.os.path.exists", return_value=True)
    @mock.patch("rally.cmd.commands.task.json.load")
    @mock.patch("rally.cmd.commands.task.open", create=True)
    def test_report_exceptions(self, mock_open, mock_json_load,
                               mock_path_exists):

        results = [
            {"key": {"name": "test", "pos": 0},
             "data": {"raw": "foo_raw", "sla": "foo_sla",
                      "load_duration": 0.1,
                      "full_duration": 1.2}}]

        mock_open.side_effect = mock.mock_open(read_data=results)
        mock_json_load.return_value = results

        ret = self.task.report(tasks="/tmp/task.json",
                               out="/tmp/tmp.hsml")

        self.assertEqual(ret, 1)
        for m in mock_open, mock_json_load:
            m.reset_mock()
        mock_path_exists.return_value = False
        ret = self.task.report(tasks="/tmp/task.json",
                               out="/tmp/tmp.hsml")
        self.assertEqual(ret, 1)

    @mock.patch("rally.cmd.commands.task.cliutils.print_list")
    @mock.patch("rally.cmd.commands.task.envutils.get_global",
                return_value="123456789")
    @mock.patch("rally.cmd.commands.task.objects.Task.list",
                return_value=[fakes.FakeTask(uuid="a",
                                             created_at=date.datetime.now(),
                                             updated_at=date.datetime.now(),
                                             status="c",
                                             tag="d",
                                             deployment_name="some_name")])
    def test_list(self, mock_objects_list, mock_default, mock_print_list):

        self.task.list(status="running")
        mock_objects_list.assert_called_once_with(
            deployment=mock_default.return_value,
            status=consts.TaskStatus.RUNNING)

        headers = ["uuid", "deployment_name", "created_at", "duration",
                   "status", "tag"]

        mock_print_list.assert_called_once_with(
            mock_objects_list.return_value, headers,
            sortby_index=headers.index("created_at"))

    def test_list_wrong_status(self):
        self.assertEqual(1, self.task.list(deployment="fake",
                                           status="wrong non existing status"))

    @mock.patch("rally.cmd.commands.task.objects.Task.list", return_value=[])
    def test_list_no_results(self, mock_list):
        self.assertIsNone(
            self.task.list(deployment="fake", all_deployments=True))
        mock_list.assert_called_once_with()
        mock_list.reset_mock()

        self.assertIsNone(
            self.task.list(deployment="d", status=consts.TaskStatus.RUNNING)
        )
        mock_list.assert_called_once_with(deployment="d",
                                          status=consts.TaskStatus.RUNNING)

    def test_delete(self):
        task_uuid = "8dcb9c5e-d60b-4022-8975-b5987c7833f7"
        force = False
        with mock.patch("rally.cmd.commands.task.api") as mock_api:
            mock_api.Task.delete = mock.Mock()
            self.task.delete(task_uuid, force=force)
            mock_api.Task.delete.assert_called_once_with(task_uuid,
                                                         force=force)

    @mock.patch("rally.cmd.commands.task.api")
    def test_delete_multiple_uuid(self, mock_api):
        task_uuids = ["4bf35b06-5916-484f-9547-12dce94902b7",
                      "52cad69d-d3e4-47e1-b445-dec9c5858fe8",
                      "6a3cb11c-ac75-41e7-8ae7-935732bfb48f",
                      "018af931-0e5a-40d5-9d6f-b13f4a3a09fc"]
        force = False
        self.task.delete(task_uuids, force=force)
        self.assertTrue(mock_api.Task.delete.call_count == len(task_uuids))
        expected_calls = [mock.call(task_uuid, force=force) for task_uuid
                          in task_uuids]
        self.assertTrue(mock_api.Task.delete.mock_calls == expected_calls)

    @mock.patch("rally.cmd.commands.task.cliutils.print_list")
    @mock.patch("rally.cmd.commands.task.objects.Task.get")
    def test_sla_check(self, mock_task_get, mock_print_list):
        data = [{"key": {"name": "fake_name",
                         "pos": "fake_pos",
                         "kw": "fake_kw"},
                 "data": {"scenario_duration": 42.0,
                          "raw": [],
                          "sla": [{"benchmark": "KeystoneBasic.create_user",
                                   "criterion": "max_seconds_per_iteration",
                                   "pos": 0,
                                   "success": False,
                                   "detail": "Max foo, actually bar"}]}}]

        mock_task_get().get_results.return_value = copy.deepcopy(data)
        result = self.task.sla_check(task_id="fake_task_id")
        self.assertEqual(1, result)
        mock_task_get.assert_called_with("fake_task_id")

        data[0]["data"]["sla"][0]["success"] = True
        mock_task_get().get_results.return_value = data

        result = self.task.sla_check(task_id="fake_task_id", tojson=True)
        self.assertEqual(0, result)

    @mock.patch("rally.cmd.commands.task.open",
                mock.mock_open(read_data="{\"some\": \"json\"}"),
                create=True)
    @mock.patch("rally.api.Task.validate")
    def test_validate(self, mock_validate):
        self.task.validate("path_to_config.json", "fake_id")
        mock_validate.assert_called_once_with("fake_id", {"some": "json"})

    @mock.patch("rally.cmd.commands.task.TaskCommands._load_task",
                side_effect=task.FailedToLoadTask)
    def test_validate_failed_to_load_task(self, mock_load):
        args = mock.MagicMock()
        args_file = mock.MagicMock()

        result = self.task.validate("path_to_task", "fake_id",
                                    task_args=args, task_args_file=args_file)
        self.assertEqual(1, result)
        mock_load.assert_called_once_with("path_to_task", args, args_file)

    @mock.patch("rally.cmd.commands.task.TaskCommands._load_task")
    @mock.patch("rally.api.Task.validate")
    def test_validate_invalid(self, mock_task_validate, mock_load):

        mock_task_validate.side_effect = exceptions.InvalidTaskException
        result = self.task.validate("path_to_task", "deployment")
        self.assertEqual(1, result)
        mock_task_validate.assert_called_once_with("deployment",
                                                   mock_load.return_value)

    @mock.patch("rally.common.fileutils._rewrite_env_file")
    @mock.patch("rally.cmd.commands.task.db.task_get", return_value=True)
    def test_use(self, mock_task, mock_file):
        task_id = "80422553-5774-44bd-98ac-38bd8c7a0feb"
        self.task.use(task_id)
        mock_file.assert_called_once_with(
            os.path.expanduser("~/.rally/globals"),
            ["RALLY_TASK=%s\n" % task_id])

    @mock.patch("rally.cmd.commands.task.db.task_get")
    def test_use_not_found(self, mock_task):
        task_id = "ddc3f8ba-082a-496d-b18f-72cdf5c10a14"
        mock_task.side_effect = exceptions.TaskNotFound(uuid=task_id)
        self.assertRaises(exceptions.TaskNotFound, self.task.use, task_id)
