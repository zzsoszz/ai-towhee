# Copyright 2021 Zilliz. All rights reserved.
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

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import torch
import torchvision
from towhee.runtime.node_config import NodeConfig
from towhee.serve.triton.model_to_triton import ModelToTriton


class Model:
    """
    Model class
    """
    def __init__(self):
        self.model = torchvision.models.resnet18(pretrained=True)

    def __call__(self, image):
        output_tensor = self.model(image)
        return output_tensor.detach().numpy()

    def save_model(self, model_type, output_file):
        if model_type != 'onnx':
            return False
        dummy_input = torch.randn(10, 3, 224, 224)
        torch.onnx.export(self.model, dummy_input, output_file, input_names=['input0'], output_names=['output0'])
        return True

    @property
    def supported_formats(self):
        return ['onnx']


op = Model()


# pylint: disable=protected-access
class TestModelToTriton(unittest.TestCase):
    """
    Test ModelToTriton
    """
    def test_to_triton(self):
        name = 'resnet18'
        server_config = {'format_priority': ['onnx', 'tensorrt']}
        node_config = NodeConfig.from_dict({'name': name})
        with TemporaryDirectory(dir='./') as root:
            m = ModelToTriton(root, op, node_config, server_config)
            self.assertTrue(m.to_triton())

            inputs, outputs = m.get_model_in_out()
            self.assertTrue(inputs, ['input0'])
            self.assertTrue(outputs, ['output0'])

            model_path = Path(root) / name
            path1 = model_path / 'config.pbtxt'
            with open(path1, encoding='utf-8') as f:
                file_config = list(f.readlines())
            pbtxt_config = ['name: "resnet18"\n',
                            'backend: "onnxruntime"\n']
            self.assertEqual(file_config, pbtxt_config)
            path2 = model_path / '1' / 'model.onnx'
            self.assertTrue(path2.exists())

    def test_prepare_conf1(self):
        name = 'resnet18_conf1'
        server_config = {'format_priority': ['onnx', 'tensorrt']}
        node_config = NodeConfig.from_dict({
            'name': name,
            'server': {
                'device_ids': [0, 1],
                'max_batch_size': 128,
                'batch_latency_micros': 100000,
                'no_key': 0,
                'triton': {
                    'preferred_batch_size': [8, 16],
                }
            }
        })
        with TemporaryDirectory(dir='./') as root:
            m = ModelToTriton(root, op, node_config, server_config)
            self.assertTrue(m.to_triton())

            model_path = Path(root) / name
            path1 = model_path / 'config.pbtxt'
            with open(path1, encoding='utf-8') as f:
                file_config = list(f.readlines())
            pbtxt_config = ['name: "resnet18_conf1"\n',
                            'backend: "onnxruntime"\n',
                            'max_batch_size: 128\n', '\n',
                            'dynamic_batching {\n', '\n',
                            '    preferred_batch_size: [8, 16]\n', '\n',
                            '    max_queue_delay_microseconds: 100000\n', '\n',
                            '}\n', '\n',
                            'instance_group [\n', '    {\n',
                            '        kind: KIND_GPU\n',
                            '        count: 1\n',
                            '        gpus: [0, 1]\n', '    }\n', ']\n']
            self.assertEqual(file_config, pbtxt_config)
            path2 = model_path / '1' / 'model.onnx'
            self.assertTrue(path2.exists())

    def test_prepare_conf2(self):
        name = 'resnet18_conf2'
        server_config = {'format_priority': ['onnx', 'tensorrt']}
        node_config = NodeConfig.from_dict({
            'name': name,
            'server': {'num_instances_per_device': 3}
        })
        with TemporaryDirectory(dir='./') as root:
            m = ModelToTriton(root, op, node_config, server_config)
            self.assertTrue(m._create_model_dir())
            self.assertTrue(m._prepare_config())

            model_path = Path(root) / name
            path1 = model_path / 'config.pbtxt'
            with open(path1, encoding='utf-8') as f:
                file_config = list(f.readlines())
            pbtxt_config = ['name: "resnet18_conf2"\n',
                            'backend: "python"\n', '\n',
                            'instance_group [\n', '    {\n',
                            '        kind: KIND_CPU\n',
                            '        count: 3\n',
                            '    }\n', ']\n']
            self.assertEqual(file_config, pbtxt_config)

