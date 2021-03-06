import os


def callback(work_path, project_name):
    return f"""import re
import os
import numpy as np
import tensorflow as tf
from loguru import logger
from tqdm.keras import TqdmCallback
from tensorflow.keras import backend as K
from {work_path}.{project_name}.settings import LR
from {work_path}.{project_name}.settings import EPOCHS
from {work_path}.{project_name}.settings import BATCH_SIZE
from {work_path}.{project_name}.settings import log_dir
from {work_path}.{project_name}.settings import csv_path
from {work_path}.{project_name}.settings import train_path
from {work_path}.{project_name}.settings import UPDATE_FREQ
from {work_path}.{project_name}.settings import LR_PATIENCE
from {work_path}.{project_name}.settings import EARLY_PATIENCE
from {work_path}.{project_name}.settings import COSINE_SCHEDULER
from {work_path}.{project_name}.settings import checkpoint_path
from {work_path}.{project_name}.settings import checkpoint_file_path
from {work_path}.{project_name}.utils import Image_Processing

# 开启可视化的命令
'''
tensorboard --logdir "logs"
'''


# 回调函数官方文档
# https://keras.io/zh/callbacks/
class CallBack(object):
    @classmethod
    def calculate_the_best_weight(self):
        if os.listdir(checkpoint_path):
            value = Image_Processing.extraction_image(checkpoint_path)
            extract_num = [os.path.splitext(os.path.split(i)[-1])[0] for i in value]
            num = [re.split('-', i) for i in extract_num]
            accs = [0 - float(i[-1]) for i in num]
            losses = [float('-' + str(abs(float(i[-2])))) for i in num]
            index = [loss for acc, loss in zip(accs, losses)]
            model_dict = dict((ind, val) for ind, val in zip(index, value))
            return model_dict.get(max(index))
        else:
            logger.debug('没有可用的检查点')

    @classmethod
    def cosine_scheduler(self):
        train_number = len(Image_Processing.extraction_image(train_path))
        warmup_epoch = int(EPOCHS * 0.2)
        total_steps = int(EPOCHS * train_number / BATCH_SIZE)
        warmup_steps = int(warmup_epoch * train_number / BATCH_SIZE)
        cosine_scheduler_callback = WarmUpCosineDecayScheduler(learning_rate_base=LR, total_steps=total_steps,
                                                               warmup_learning_rate=LR * 0.1,
                                                               warmup_steps=warmup_steps,
                                                               hold_base_rate_steps=train_number,
                                                               min_learn_rate=LR * 0.2)
        return cosine_scheduler_callback

    @classmethod
    def callback(self, model):
        call = []
        if os.path.exists(checkpoint_path):
            if os.listdir(checkpoint_path):
                logger.debug('load the model')
                model.load_weights(os.path.join(checkpoint_path, self.calculate_the_best_weight()))
                logger.debug(f'读取的权重为{{os.path.join(checkpoint_path, self.calculate_the_best_weight())}}')

        cp_callback = tf.keras.callbacks.ModelCheckpoint(filepath=checkpoint_file_path,
                                                         verbose=1,
                                                         save_weights_only=True,
                                                         save_best_only=True, period=1)
        call.append(cp_callback)
        tensorboard_callback = tf.keras.callbacks.TensorBoard(log_dir=log_dir, histogram_freq=1, write_images=True,
                                                              update_freq=UPDATE_FREQ, write_graph=False)
        call.append(tensorboard_callback)
        if COSINE_SCHEDULER:
            lr_callback = self.cosine_scheduler()
        else:
            lr_callback = tf.keras.callbacks.ReduceLROnPlateau(factor=0.01, patience=LR_PATIENCE)
        call.append(lr_callback)

        csv_callback = tf.keras.callbacks.CSVLogger(filename=csv_path, append=True)
        call.append(csv_callback)

        early_callback = tf.keras.callbacks.EarlyStopping(min_delta=0, verbose=1, patience=EARLY_PATIENCE)
        call.append(early_callback)
        call.append(TqdmCallback())
        return (model, call)


class WarmUpCosineDecayScheduler(tf.keras.callbacks.Callback):
    def __init__(self, learning_rate_base, total_steps, global_step_init=0, warmup_learning_rate=0.0, warmup_steps=0,
                 hold_base_rate_steps=0, min_learn_rate=0., verbose=1):
        super(WarmUpCosineDecayScheduler, self).__init__()
        # 基础的学习率
        self.learning_rate_base = learning_rate_base
        # 热调整参数
        self.warmup_learning_rate = warmup_learning_rate
        # 参数显示
        self.verbose = verbose
        # learning_rates用于记录每次更新后的学习率，方便图形化观察
        self.min_learn_rate = min_learn_rate
        self.learning_rates = []

        self.interval_epoch = [0.05, 0.15, 0.30, 0.50]
        # 贯穿全局的步长
        self.global_step_for_interval = global_step_init
        # 用于上升的总步长
        self.warmup_steps_for_interval = warmup_steps
        # 保持最高峰的总步长
        self.hold_steps_for_interval = hold_base_rate_steps
        # 整个训练的总步长
        self.total_steps_for_interval = total_steps

        self.interval_index = 0
        # 计算出来两个最低点的间隔
        self.interval_reset = [self.interval_epoch[0]]
        for i in range(len(self.interval_epoch) - 1):
            self.interval_reset.append(self.interval_epoch[i + 1] - self.interval_epoch[i])
        self.interval_reset.append(1 - self.interval_epoch[-1])

    def cosine_decay_with_warmup(self, global_step, learning_rate_base, total_steps, warmup_learning_rate=0.0,
                                 warmup_steps=0,
                                 hold_base_rate_steps=0, min_learn_rate=0, ):
        if total_steps < warmup_steps:
            raise ValueError('total_steps must be larger or equal to '
                             'warmup_steps.')
        # 这里实现了余弦退火的原理，设置学习率的最小值为0，所以简化了表达式
        learning_rate = 0.5 * learning_rate_base * (1 + np.cos(np.pi *
                                                               (
                                                                       global_step - warmup_steps - hold_base_rate_steps) / float(
            total_steps - warmup_steps - hold_base_rate_steps)))
        # 如果hold_base_rate_steps大于0，表明在warm up结束后学习率在一定步数内保持不变
        if hold_base_rate_steps > 0:
            learning_rate = np.where(global_step > warmup_steps + hold_base_rate_steps,
                                     learning_rate, learning_rate_base)
        if warmup_steps > 0:
            if learning_rate_base < warmup_learning_rate:
                raise ValueError('learning_rate_base must be larger or equal to '
                                 'warmup_learning_rate.')
            # 线性增长的实现
            slope = (learning_rate_base - warmup_learning_rate) / warmup_steps
            warmup_rate = slope * global_step + warmup_learning_rate
            # 只有当global_step 仍然处于warm up阶段才会使用线性增长的学习率warmup_rate，否则使用余弦退火的学习率learning_rate
            learning_rate = np.where(global_step < warmup_steps, warmup_rate,
                                     learning_rate)

        learning_rate = max(learning_rate, min_learn_rate)
        return learning_rate

    # 更新global_step，并记录当前学习率
    def on_batch_end(self, batch, logs=None):
        self.global_step = self.global_step + 1
        self.global_step_for_interval = self.global_step_for_interval + 1
        lr = K.get_value(self.model.optimizer.lr)
        self.learning_rates.append(lr)

    # 更新学习率
    def on_batch_begin(self, batch, logs=None):
        # 每到一次最低点就重新更新参数
        if self.global_step_for_interval in [0] + [int(i * self.total_steps_for_interval) for i in self.interval_epoch]:
            self.total_steps = self.total_steps_for_interval * self.interval_reset[self.interval_index]
            self.warmup_steps = self.warmup_steps_for_interval * self.interval_reset[self.interval_index]
            self.hold_base_rate_steps = self.hold_steps_for_interval * self.interval_reset[self.interval_index]
            self.global_step = 0
            self.interval_index += 1

        lr = self.cosine_decay_with_warmup(global_step=self.global_step,
                                           learning_rate_base=self.learning_rate_base,
                                           total_steps=self.total_steps,
                                           warmup_learning_rate=self.warmup_learning_rate,
                                           warmup_steps=self.warmup_steps,
                                           hold_base_rate_steps=self.hold_base_rate_steps,
                                           min_learn_rate=self.min_learn_rate)
        K.set_value(self.model.optimizer.lr, lr)
        if self.verbose > 0:
            logger.info(f'Batch {{self.global_step}}: setting learning rate to {{lr}}.')


if __name__ == '__main__':
    logger.debug(CallBack.calculate_the_best_weight())

"""


def app(work_path, project_name):
    return f"""import os
import json
import operator
import tensorflow as tf
from flask import Flask
from flask import request
from loguru import logger
from {work_path}.{project_name}.models import Models
from {work_path}.{project_name}.settings import USE_GPU
from {work_path}.{project_name}.settings import MODEL
from {work_path}.{project_name}.settings import MODEL_NAME
from {work_path}.{project_name}.settings import n_class_file
from {work_path}.{project_name}.settings import checkpoint_path
from {work_path}.{project_name}.settings import App_model_path
from {work_path}.{project_name}.callback import CallBack
from {work_path}.{project_name}.utils import Predict_Image


if USE_GPU:
    gpus = tf.config.experimental.list_physical_devices(device_type="GPU")
    if gpus:
        logger.info("use gpu device")
        logger.info(f'可用GPU数量: {{len(gpus)}}')
        try:
            tf.config.experimental.set_visible_devices(gpus[0], 'GPU')
        except RuntimeError as e:
            logger.error(e)
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(device=gpu, enable=True)
            tf.print(gpu)
    else:
        tf.config.experimental.list_physical_devices(device_type="CPU")
        os.environ["CUDA_VISIBLE_DEVICE"] = "-1"
        logger.info("not found gpu device,convert to use cpu")
else:
    logger.info("use cpu device")
    # 禁用gpu
    tf.config.experimental.list_physical_devices(device_type="CPU")
    os.environ["CUDA_VISIBLE_DEVICE"] = "-1"

app = Flask(__name__)
if App_model_path:
    model_path = os.path.join(App_model_path,os.listdir(App_model_path)[0])
    logger.debug(f'{{model_path}}模型加载成功')
else:
    model = operator.methodcaller(MODEL)(Models)
    try:
        model.load_weights(os.path.join(checkpoint_path, CallBack.calculate_the_best_weight()))
    except:
        raise OSError(f'没有任何的权重和模型在{{App_model_path}}')
    model_path = os.path.join(App_model_path, MODEL_NAME)
    model.save(model_path)
    logger.debug(f'{{model_path}}模型加载成功')

model = tf.keras.models.load_model(model_path)


@app.route("/", methods=['POST'])
def captcha_predict():
    return_dict = {{'return_code': '200', 'return_info': '处理成功', 'result': False, 'recognition_rate': 0, 'time': None}}
    get_data = request.form.to_dict()
    if 'img' in get_data.keys():
        base64_str = request.form['img']
        try:
            result, recognition_rate, times = Predict_Image(model, image=base64_str, num_classes=n_class_file).api()
            return_dict['time'] = str(times)
            return_dict['result'] = str(result)
            return_dict['recognition_rate'] = str(recognition_rate)
        except Exception as e:
            return_dict['result'] = str(e)
            return_dict['return_info'] = '模型识别错误'
    else:
        return_dict['return_code'] = '5004'
        return_dict['return_info'] = '参数错误，没有img属性'
    logger.debug(return_dict)
    return json.dumps(return_dict, ensure_ascii=False)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5006, debug=True)

"""


def captcha_config():
    return '''{
  "train_dir": "train_dataset",
  "validation_dir": "validation_dataset",
  "test_dir": "test_dataset",
  "image_suffix": "jpg",
  "characters": "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
  "count": 20000,
  "char_count": [4,5,6],
  "width": 100,
  "height": 60
}
'''


def check_file(work_path, project_name):
    return f"""import numpy as np
from PIL import Image
from loguru import logger
from {work_path}.{project_name}.settings import train_path
from {work_path}.{project_name}.settings import validation_path
from {work_path}.{project_name}.settings import test_path
from {work_path}.{project_name}.settings import train_enhance_path
from {work_path}.{project_name}.settings import DATA_ENHANCEMENT
from {work_path}.{project_name}.utils import Image_Processing
from concurrent.futures import ThreadPoolExecutor

if DATA_ENHANCEMENT:
    train_image = Image_Processing.extraction_image(train_enhance_path)
else:
    train_image = Image_Processing.extraction_image(train_path)


def cheak_image(image):
    with open(image, 'rb') as image_file:
        image = Image.open(image_file)
        if image.mode != 'RGB':
            logger.error(f'{{image}}模式为{{image.mode}}')
            return False
        width, height = image.size
        width_list.append(width)
        height_list.append(height)



validation_image = Image_Processing.extraction_image(validation_path)

test_image = Image_Processing.extraction_image(test_path)

width_list = []
height_list = []

image_list = train_image + validation_image + test_image

with ThreadPoolExecutor(max_workers=500) as t:
    for i in image_list:
        task = t.submit(cheak_image, i)

logger.info(f'所有图片最大的高为{{np.max(height_list)}}')
logger.info(f'所有图片最大的宽为{{np.max(width_list)}}')

"""


def delete_file(work_path, project_name):
    return f"""# 增强后文件太多，手动删非常困难，直接用代码删
import shutil
from tqdm import tqdm
from loguru import logger
from {work_path}.{project_name}.settings import train_path
from {work_path}.{project_name}.settings import test_path
from {work_path}.{project_name}.settings import validation_path
from {work_path}.{project_name}.settings import train_enhance_path
from {work_path}.{project_name}.settings import train_pack_path
from {work_path}.{project_name}.settings import validation_pack_path
from {work_path}.{project_name}.settings import test_pack_path
from concurrent.futures import ThreadPoolExecutor


def del_file(path):
    try:
        shutil.rmtree(path)
        logger.debug(f'成功删除{{path}}')
    except WindowsError as e:
        logger.error(e)


if __name__ == '__main__':
    path = [train_path, test_path, validation_path, train_enhance_path, train_pack_path, validation_pack_path,
            test_pack_path]
    with ThreadPoolExecutor(max_workers=7) as t:
        for i in tqdm(path, desc='正在删除'):
            t.submit(del_file, i)
"""


def utils(work_path, project_name):
    return f"""import io
import re
import os
import json
import time
import shutil
import base64
import random
import numpy as np
from tqdm import tqdm
from PIL import Image
import tensorflow as tf
from loguru import logger
from PIL import ImageFilter
from PIL import ImageEnhance
import matplotlib.pyplot as plt
from matplotlib.image import imread
from matplotlib.patches import Rectangle
from {work_path}.{project_name}.settings import n_class_file
from {work_path}.{project_name}.settings import validation_path
from {work_path}.{project_name}.settings import test_path
from {work_path}.{project_name}.settings import train_enhance_path
from {work_path}.{project_name}.settings import MODE
from {work_path}.{project_name}.settings import IMAGE_HEIGHT
from {work_path}.{project_name}.settings import IMAGE_WIDTH
from {work_path}.{project_name}.settings import CAPTCHA_LENGTH
from {work_path}.{project_name}.settings import IMAGE_CHANNALS
from {work_path}.{project_name}.settings import DATA_ENHANCEMENT
from concurrent.futures import ThreadPoolExecutor

right_value = 0
predicted_value = 0


class Image_Processing(object):
    @classmethod
    # 提取全部图片plus
    def extraction_image(self, path: str, mode=MODE) -> list:
        try:
            data_path = []
            datas = [os.path.join(path, i) for i in os.listdir(path)]
            for data in datas:
                data_path = data_path + [os.path.join(data, i) for i in os.listdir(data)]
            return data_path
        except:
            return [os.path.join(path, i) for i in os.listdir(path)]

    @classmethod
    def extraction_label(self, path_list: list, suffix=True, divide='_', mode=MODE):
        if mode == 'ORDINARY':
            if suffix:
                paths = [os.path.splitext(os.path.split(i)[-1])[0] for i in path_list]
                paths = [re.split(divide, i)[0] for i in paths]
                ocr_path = []
                for i in paths:
                    for s in i:
                        ocr_path.append(s)
                n_class = sorted(set(ocr_path))
                save_dict = dict((index, name) for index, name in enumerate(n_class))
                if not os.path.exists(os.path.join(os.getcwd(), n_class_file)):
                    with open(n_class_file, 'w', encoding='utf-8') as f:
                        f.write(json.dumps(save_dict, ensure_ascii=False))
                with open(n_class_file, 'r', encoding='utf-8') as f:
                    make_dict = json.loads(f.read())
                make_dict = dict((name, index) for index, name in make_dict.items())
                label_list = [self.text2vector(label, make_dict=make_dict) for label in paths]
                return label_list
            else:
                paths = [os.path.splitext(os.path.split(i)[-1])[0] for i in path_list]
                ocr_path = []
                for i in paths:
                    for s in i:
                        ocr_path.append(s)
                n_class = sorted(set(ocr_path))
                save_dict = dict((index, name) for index, name in enumerate(n_class))
                if not os.path.exists(os.path.join(os.getcwd(), n_class_file)):
                    with open(n_class_file, 'w', encoding='utf-8') as f:
                        f.write(json.dumps(save_dict, ensure_ascii=False))
                with open(n_class_file, 'r', encoding='utf-8') as f:
                    make_dict = json.loads(f.read())
                make_dict = dict((name, index) for index, name in make_dict.items())
                label_list = [self.text2vector(label, make_dict=make_dict) for label in paths]
                return label_list
        elif mode == 'NUM_CLASSES':
            if suffix:
                paths = [os.path.splitext(os.path.split(i)[-1])[0] for i in path_list]
                paths = [re.split(divide, i)[0] for i in paths]
                n_class = sorted(set(paths))
                save_dict = dict((index, name) for index, name in enumerate(n_class))
                if not os.path.exists(os.path.join(os.getcwd(), n_class_file)):
                    with open(n_class_file, 'w', encoding='utf-8') as f:
                        f.write(json.dumps(save_dict, ensure_ascii=False))
                with open(n_class_file, 'r', encoding='utf-8') as f:
                    make_dict = json.loads(f.read())
                make_dict = dict((name, index) for index, name in make_dict.items())
                label_list = [self.text2vector(label, make_dict=make_dict, mode=MODE) for label in paths]
                return label_list
            else:
                paths = [os.path.splitext(os.path.split(i)[-1])[0] for i in path_list]
                n_class = sorted(set(paths))
                save_dict = dict((index, name) for index, name in enumerate(n_class))
                if not os.path.exists(os.path.join(os.getcwd(), n_class_file)):
                    with open(n_class_file, 'w', encoding='utf-8') as f:
                        f.write(json.dumps(save_dict, ensure_ascii=False))
                with open(n_class_file, 'r', encoding='utf-8') as f:
                    make_dict = json.loads(f.read())
                make_dict = dict((name, index) for index, name in make_dict.items())
                label_list = [self.text2vector(label, make_dict=make_dict, mode=MODE) for label in paths]
                return label_list
        elif mode == 'CTC':
            if suffix:
                paths = [os.path.splitext(os.path.split(i)[-1])[0] for i in path_list]
                paths = [re.split(divide, i)[0] for i in paths]
                ocr_path = []
                for i in paths:
                    for s in i:
                        ocr_path.append(s)
                n_class = sorted(set(ocr_path))
                save_dict = dict((index, name) for index, name in enumerate(n_class))
                if not os.path.exists(os.path.join(os.getcwd(), n_class_file)):
                    with open(n_class_file, 'w', encoding='utf-8') as f:
                        f.write(json.dumps(save_dict, ensure_ascii=False))
                with open(n_class_file, 'r', encoding='utf-8') as f:
                    make_dict = json.loads(f.read())
                make_dict = dict((name, index) for index, name in make_dict.items())
                label_list = [self.text2vector(label, make_dict=make_dict) for label in paths]
                return label_list
            else:
                paths = [os.path.splitext(os.path.split(i)[-1])[0] for i in path_list]
                ocr_path = []
                for i in paths:
                    for s in i:
                        ocr_path.append(s)
                n_class = sorted(set(ocr_path))
                save_dict = dict((index, name) for index, name in enumerate(n_class))
                if not os.path.exists(os.path.join(os.getcwd(), n_class_file)):
                    with open(n_class_file, 'w', encoding='utf-8') as f:
                        f.write(json.dumps(save_dict, ensure_ascii=False))
                with open(n_class_file, 'r', encoding='utf-8') as f:
                    make_dict = json.loads(f.read())
                make_dict = dict((name, index) for index, name in make_dict.items())
                label_list = [self.text2vector(label, make_dict=make_dict) for label in paths]
                return label_list
        else:
            raise ValueError(f'没有mode={{mode}}提取标签的方法')

    @classmethod
    def text2vector(self, label, make_dict: dict, mode=MODE):
        if mode == 'ORDINARY':
            if len(label) > CAPTCHA_LENGTH:
                raise ValueError(f'标签{{label}}长度大于预设值{{label}},建议设置CAPTCHA_LENGTH为{{len(label) + 2}}')
            num_classes = len(make_dict)
            label_ver = np.ones((CAPTCHA_LENGTH), dtype=np.int64) * num_classes
            for index, c in enumerate(label):
                if not make_dict.get(c):
                    raise ValueError(f'错误的值{{c}}')
                label_ver[index] = make_dict.get(c)
            label_ver = list(tf.keras.utils.to_categorical(label_ver, num_classes=num_classes + 1).ravel())
            return label_ver
        elif mode == 'NUM_CLASSES':
            num_classes = len(make_dict)
            label_ver = np.zeros((num_classes), dtype=np.int64) * num_classes
            label_ver[int(make_dict.get(label))] = 1.
            return label_ver
        elif mode == 'CTC':
            label_ver = []
            for c in label:
                if not make_dict.get(c):
                    raise ValueError(f'错误的值{{c}}')
                label_ver.append(int(make_dict.get(c)))
            label_ver = np.array(label_ver)
            return label_ver
        else:
            raise ValueError(f'没有mode={{mode}}提取标签的方法')

    @classmethod
    def _shutil_move(self, full_path, des_path, number):
        shutil.move(full_path, des_path)
        logger.info(f'剩余数量{{number}}')

    # 分割数据集
    @classmethod
    def move_path(self, path: list, proportion=0.2) -> bool:
        number = 0
        logger.debug(f'数据集有{{len(path)}},{{proportion * 100}}%作为验证集,{{proportion * 100}}%作为测试集')
        division_number = int(len(path) * proportion)
        logger.debug(f'验证集数量为{{division_number}},测试集数量为{{division_number}}')
        validation_dataset = random.sample(path, division_number)
        with ThreadPoolExecutor(max_workers=500) as t:
            for i in validation_dataset:
                number = number + 1
                logger.debug(f'准备移动{{(number / len(validation_dataset)) * 100}}%')
                t.submit(path.remove, i)
        validation = [os.path.join(validation_path, os.path.split(i)[-1]) for i in validation_dataset]
        validation_lenght = len(validation)
        with ThreadPoolExecutor(max_workers=50) as t:
            for full_path, des_path in zip(validation_dataset, validation):
                validation_lenght = validation_lenght - 1
                t.submit(Image_Processing._shutil_move, full_path, des_path, validation_lenght)
        test_dataset = random.sample(path, division_number)
        test = [os.path.join(test_path, os.path.split(i)[-1]) for i in test_dataset]
        test_lenght = len(test)
        with ThreadPoolExecutor(max_workers=50) as t:
            for full_path, des_path in zip(test_dataset, test):
                test_lenght = test_lenght - 1
                t.submit(Image_Processing._shutil_move, full_path, des_path, test_lenght)
        logger.info(f'任务结束')
        return True

    # 修改文件名
    @classmethod
    def rename_path(self, path: list, original='.', reform='_'):
        for i in tqdm(path, desc='正在改名'):
            paths, name = os.path.split(i)
            name, mix = os.path.splitext(name)
            if original in name:
                new_name = name.replace(original, reform)
                os.rename(i, os.path.join(paths, new_name + mix))

    @classmethod
    def rename_suffix(self, path: list):
        for i in tqdm(path, desc='正在修改后缀'):
            paths, name = os.path.split(i)
            name, mix = os.path.splitext(name)
            os.rename(i, os.path.join(paths, name + '.jpg'))

    # # 增强图片
    # @classmethod
    # def preprosess_save_images(self, image, number):
    #     logger.info(f'开始处理{{image}}')
    #     with open(image, 'rb') as images:
    #         im = Image.open(images)
    #         blur_im = im.filter(ImageFilter.BLUR)
    #         contour_im = im.filter(ImageFilter.CONTOUR)
    #         detail_im = im.filter(ImageFilter.DETAIL)
    #         edge_enhance_im = im.filter(ImageFilter.EDGE_ENHANCE)
    #         edge_enhance_more_im = im.filter(ImageFilter.EDGE_ENHANCE_MORE)
    #         emboss_im = im.filter(ImageFilter.EMBOSS)
    #         flnd_edges_im = im.filter(ImageFilter.FIND_EDGES)
    #         smooth_im = im.filter(ImageFilter.SMOOTH)
    #         smooth_more_im = im.filter(ImageFilter.SMOOTH_MORE)
    #         sharpen_im = im.filter(ImageFilter.SHARPEN)
    #         maxfilter_im = im.filter(ImageFilter.MaxFilter)
    #         minfilter_im = im.filter(ImageFilter.MinFilter)
    #         modefilter_im = im.filter(ImageFilter.ModeFilter)
    #         medianfilter_im = im.filter(ImageFilter.MedianFilter)
    #         unsharpmask_im = im.filter(ImageFilter.UnsharpMask)
    #         left_right_im = im.transpose(Image.FLIP_LEFT_RIGHT)
    #         top_bottom_im = im.transpose(Image.FLIP_TOP_BOTTOM)
    #         rotate_list = [im.rotate(i) for i in list(range(1, 360, 60))]
    #         brightness_im = ImageEnhance.Brightness(im).enhance(0.5)
    #         brightness_up_im = ImageEnhance.Brightness(im).enhance(1.5)
    #         color_im = ImageEnhance.Color(im).enhance(0.5)
    #         color_up_im = ImageEnhance.Color(im).enhance(1.5)
    #         contrast_im = ImageEnhance.Contrast(im).enhance(0.5)
    #         contrast_up_im = ImageEnhance.Contrast(im).enhance(1.5)
    #         sharpness_im = ImageEnhance.Sharpness(im).enhance(0.5)
    #         sharpness_up_im = ImageEnhance.Sharpness(im).enhance(1.5)
    #         image_list = [im, blur_im, contour_im, detail_im, edge_enhance_im, edge_enhance_more_im, emboss_im,
    #                       flnd_edges_im,
    #                       smooth_im, smooth_more_im, sharpen_im, maxfilter_im, minfilter_im, modefilter_im,
    #                       medianfilter_im,
    #                       unsharpmask_im, left_right_im,
    #                       top_bottom_im, brightness_im, brightness_up_im, color_im, color_up_im, contrast_im,
    #                       contrast_up_im, sharpness_im, sharpness_up_im] + rotate_list
    #         for index, file in enumerate(image_list):
    #             paths, files = os.path.split(image)
    #             files, suffix = os.path.splitext(files)
    #             new_file = os.path.join(paths, train_enhance_path, files + str(index) + suffix)
    #             file.save(new_file)
    #     logger.success(f'处理完成{{image}},还剩{{number}}张图片待增强')

    @classmethod
    def preprosess_save_images(self, image, number):
        logger.info(f'开始处理{{image}}')
        name = os.path.splitext(image)[0]
        datagen = tf.keras.preprocessing.image.ImageDataGenerator(featurewise_center=False,
                                                                  samplewise_center=False,
                                                                  featurewise_std_normalization=False,
                                                                  samplewise_std_normalization=False,
                                                                  zca_whitening=False,
                                                                  zca_epsilon=1e-6,
                                                                  rotation_range=40,
                                                                  width_shift_range=0.2,
                                                                  height_shift_range=0.2,
                                                                  brightness_range=(0.7, 1.3),
                                                                  shear_range=30,
                                                                  zoom_range=0.2,
                                                                  channel_shift_range=0.,
                                                                  fill_mode='nearest',
                                                                  cval=0.,
                                                                  horizontal_flip=False,
                                                                  vertical_flip=False,
                                                                  rescale=1 / 255,
                                                                  preprocessing_function=None,
                                                                  data_format=None,
                                                                  validation_split=0.0,
                                                                  dtype=None)
        shutil.copy(image, train_enhance_path)
        img = tf.keras.preprocessing.image.load_img(image)
        x = tf.keras.preprocessing.image.img_to_array(img)
        x = np.expand_dims(x, 0)
        i = 0
        for _ in datagen.flow(x, batch_size=1, save_to_dir=train_enhance_path, save_prefix=name, save_format='jpg'):
            i += 1
            if i == DATA_ENHANCEMENT:
                break
        logger.success(f'处理完成{{image}},还剩{{number}}张图片待增强')

    @classmethod
    # 展示图片处理后的效果
    def show_image(self, image_path):
        '''
        展示图片处理后的效果
        :param image_path:
        :return:
        '''
        image = Image.open(image_path)
        while True:
            width, height = image.size
            if IMAGE_HEIGHT < height:
                resize_width = int(IMAGE_HEIGHT / height * width)
                image = image.resize((resize_width, IMAGE_HEIGHT))
            if IMAGE_WIDTH < width:
                resize_height = int(IMAGE_WIDTH / width * height)
                image = image.resize((IMAGE_WIDTH, resize_height))
            if IMAGE_WIDTH >= width and IMAGE_HEIGHT >= height:
                break
        width, height = image.size
        image = np.array(image)
        image = np.pad(image, ((0, IMAGE_HEIGHT - height), (0, IMAGE_WIDTH - width), (0, 0)), 'constant',
                       constant_values=0)
        image = Image.fromarray(image)
        image_bytearr = io.BytesIO()
        image.save(image_bytearr, format='JPEG')
        plt.imshow(image)
        plt.show()

    @classmethod
    # 图片画框
    def tagging_image(self, image_path, box):
        im = imread(image_path)
        plt.figure()
        plt.imshow(im)
        ax = plt.gca()
        x = box[0]
        y = box[1]
        w = box[2]
        h = box[3]
        rect = Rectangle((x, y), w, h, linewidth=1, edgecolor='r', facecolor='none')
        ax.add_patch(rect)
        plt.show()

    @classmethod
    # 对图片进行解码,预测
    def load_image(self, image):
        try:
            with open(image, 'rb') as image_file:
                image = Image.open(image_file)
            while True:
                width, height = image.size
                if IMAGE_HEIGHT < height:
                    resize_width = int(IMAGE_HEIGHT / height * width)
                    image = image.resize((resize_width, IMAGE_HEIGHT))
                if IMAGE_WIDTH < width:
                    resize_height = int(IMAGE_WIDTH / width * height)
                    image = image.resize((IMAGE_WIDTH, resize_height))
                if IMAGE_WIDTH >= width and IMAGE_HEIGHT >= height:
                    break
                width, height = image.size
                image = np.array(image)
                image = np.pad(image, ((0, IMAGE_HEIGHT - height), (0, IMAGE_WIDTH - width), (0, 0)), 'constant',
                               constant_values=0)
                image = np.expand_dims(image, axis=0)
                image = image / 255.
                image_file.close()
            return image
        except IOError as e:
            logger.error(e)
            raise IOError('IO错误')


# 打包数据
class WriteTFRecord(object):
    @staticmethod
    def pad_image(image_path):
        image = Image.open(image_path)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        while True:
            width, height = image.size
            if IMAGE_HEIGHT < height:
                resize_width = int(IMAGE_HEIGHT / height * width)
                image = image.resize((resize_width, IMAGE_HEIGHT))
            if IMAGE_WIDTH < width:
                resize_height = int(IMAGE_WIDTH / width * height)
                image = image.resize((IMAGE_WIDTH, resize_height))
            if IMAGE_WIDTH >= width and IMAGE_HEIGHT >= height:
                break
        width, height = image.size
        image = np.array(image)
        image = np.pad(image, ((0, IMAGE_HEIGHT - height), (0, IMAGE_WIDTH - width), (0, 0)), 'constant',
                       constant_values=0)
        image = Image.fromarray(image)
        image_bytearr = io.BytesIO()
        image.save(image_bytearr, format='JPEG')
        # plt.imshow(image)
        # plt.show()
        image_bytes = image_bytearr.getvalue()
        return image_bytes

    @staticmethod
    def WriteTFRecord(TFRecord_path, datasets: list, labels: list, file_name='dataset', spilt=100, mode=MODE):
        number = 0
        if mode == 'CTC':
            num_count = len(datasets)
            labels_count = len(labels)
            if not os.path.exists(TFRecord_path):
                os.mkdir(TFRecord_path)
            logger.info(f'文件个数为:{{num_count}}')
            logger.info(f'标签个数为:{{labels_count}}')
            while True:
                if datasets:
                    number = number + 1
                    image_list = datasets[:spilt]
                    label_list = labels[:spilt]
                    for i in image_list:
                        datasets.remove(i)
                    for i in label_list:
                        labels.remove(i)
                    filename = file_name + str(number) + '.tfrecords'
                    filename = os.path.join(TFRecord_path, filename)
                    writer = tf.io.TFRecordWriter(filename)
                    logger.info(f'开始保存{{filename}}')
                    for image, label in zip(image_list, label_list):
                        num_count = num_count - 1
                        image_bytes = WriteTFRecord.pad_image(image)
                        logger.debug(f'剩余{{num_count}}图片待打包')
                        example = tf.train.Example(
                            features=tf.train.Features(
                                feature={{'image': tf.train.Feature(bytes_list=tf.train.BytesList(value=[image_bytes])),
                                         'label': tf.train.Feature(int64_list=tf.train.Int64List(value=label))}}))
                        # 序列化
                        serialized = example.SerializeToString()
                        writer.write(serialized)
                    logger.info(f'保存{{filename}}成功')
                    writer.close()
                else:
                    return None
        else:
            num_count = len(datasets)
            labels_count = len(labels)
            if not os.path.exists(TFRecord_path):
                os.mkdir(TFRecord_path)
            logger.info(f'文件个数为:{{num_count}}')
            logger.info(f'标签个数为:{{labels_count}}')
            while True:
                if datasets:
                    number = number + 1
                    image_list = datasets[:spilt]
                    label_list = labels[:spilt]
                    for i in image_list:
                        datasets.remove(i)
                    for i in label_list:
                        labels.remove(i)
                    filename = file_name + str(number) + '.tfrecords'
                    filename = os.path.join(TFRecord_path, filename)
                    writer = tf.io.TFRecordWriter(filename)
                    logger.info(f'开始保存{{filename}}')
                    for image, label in zip(image_list, label_list):
                        num_count = num_count - 1
                        image_bytes = WriteTFRecord.pad_image(image)
                        logger.debug(f'剩余{{num_count}}图片待打包')
                        example = tf.train.Example(
                            features=tf.train.Features(
                                feature={{'image': tf.train.Feature(bytes_list=tf.train.BytesList(value=[image_bytes])),
                                         'label': tf.train.Feature(float_list=tf.train.FloatList(value=label))}}))
                        # 序列化
                        serialized = example.SerializeToString()
                        writer.write(serialized)
                    logger.info(f'保存{{filename}}成功')
                    writer.close()
                else:
                    return None


# 映射函数
def parse_function(exam_proto, mode=MODE):
    if mode == 'ORDINARY':
        with open(n_class_file, 'r', encoding='utf-8') as f:
            make_dict = json.loads(f.read())
        features = {{
            'image': tf.io.FixedLenFeature([], tf.string),
            'label': tf.io.FixedLenFeature([CAPTCHA_LENGTH, len(make_dict) + 1], tf.float32)
        }}
        parsed_example = tf.io.parse_single_example(exam_proto, features)
        img_tensor = tf.image.decode_jpeg(parsed_example['image'], channels=IMAGE_CHANNALS)
        img_tensor = tf.image.resize(img_tensor, [IMAGE_HEIGHT, IMAGE_WIDTH])
        img_tensor = img_tensor / 255.
        label_tensor = parsed_example['label']
        return (img_tensor, label_tensor)
    elif mode == 'NUM_CLASSES':
        with open(n_class_file, 'r', encoding='utf-8') as f:
            make_dict = json.loads(f.read())
        features = {{
            'image': tf.io.FixedLenFeature([], tf.string),
            'label': tf.io.FixedLenFeature([len(make_dict)], tf.float32)
        }}
        parsed_example = tf.io.parse_single_example(exam_proto, features)
        img_tensor = tf.image.decode_jpeg(parsed_example['image'], channels=IMAGE_CHANNALS)
        img_tensor = tf.image.resize(img_tensor, [IMAGE_HEIGHT, IMAGE_WIDTH])
        img_tensor = img_tensor / 255.
        label_tensor = parsed_example['label']
        return (img_tensor, label_tensor)

    elif mode == 'CTC':
        features = {{
            'image': tf.io.FixedLenFeature([], tf.string),
            'label': tf.io.VarLenFeature(tf.int64)
        }}
        parsed_example = tf.io.parse_single_example(exam_proto, features)
        img_tensor = tf.image.decode_jpeg(parsed_example['image'], channels=IMAGE_CHANNALS)
        img_tensor = tf.image.resize(img_tensor, [IMAGE_HEIGHT, IMAGE_WIDTH])
        img_tensor = img_tensor / 255.
        label_tensor = parsed_example['label']
        return (img_tensor, label_tensor)
    else:
        raise ValueError(f'没有mode={{mode}}映射的方法')


class Predict_Image(object):
    def __init__(self, model=None, image=None, num_classes=str, mode=MODE):
        self.model = model
        self.image = image
        self.num_classes = num_classes
        self.mode = mode

    def decode_image(self, image):
        try:
            with open(image, 'rb') as image_file:
                image = Image.open(image_file)
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                while True:
                    width, height = image.size
                    if IMAGE_HEIGHT < height:
                        resize_width = int(IMAGE_HEIGHT / height * width)
                        image = image.resize((resize_width, IMAGE_HEIGHT))
                    if IMAGE_WIDTH < width:
                        resize_height = int(IMAGE_WIDTH / width * height)
                        image = image.resize((IMAGE_WIDTH, resize_height))
                    if IMAGE_WIDTH >= width and IMAGE_HEIGHT >= height:
                        break
                width, height = image.size
                image = np.array(image)
                image = np.pad(image, ((0, IMAGE_HEIGHT - height), (0, IMAGE_WIDTH - width), (0, 0)), 'constant',
                               constant_values=0)
                image = np.expand_dims(image, axis=0)
                image = image / 255.
                image_file.close()
            return image
        except:
            try:
                image_file = io.BytesIO(image)
                image = Image.open(image_file)
                if image.mode != "RGB":
                    image = image.convert('RGB')
                while True:
                    width, height = image.size
                    if IMAGE_HEIGHT < height:
                        resize_width = int(IMAGE_HEIGHT / height * width)
                        image = image.resize((resize_width, IMAGE_HEIGHT))
                    if IMAGE_WIDTH < width:
                        resize_height = int(IMAGE_WIDTH / width * height)
                        image = image.resize((IMAGE_WIDTH, resize_height))
                    if IMAGE_WIDTH >= width and IMAGE_HEIGHT >= height:
                        break
                width, height = image.size
                image = np.array(image)
                image = np.pad(image, ((0, IMAGE_HEIGHT - height), (0, IMAGE_WIDTH - width), (0, 0)), 'constant',
                               constant_values=0)
                image = np.expand_dims(image, axis=0)
                image = image / 255.
                return image
            except Exception as e:
                logger.error(e)

    def decode_label(self):
        path, label = os.path.split(self.image)
        label, suffix = os.path.splitext(label)
        label = re.split('_', label)[0]
        return label

    def recognition_probability(self, recognition_rate_liat):
        mean_section = np.mean(recognition_rate_liat)
        std_section = np.std(recognition_rate_liat)
        sqrt_section = np.sqrt(len(recognition_rate_liat))
        min_confidence = mean_section - (2.58 * (std_section / sqrt_section))
        return min_confidence

    def decode_vector(self, vector, num_classes):
        with open(num_classes, 'r', encoding='utf-8') as f:
            num_classes = json.loads(f.read())
        text_list = []
        recognition_rate_liat = []
        if self.mode == 'ORDINARY':
            vector = vector[0]
            for i in vector:
                text = num_classes.get(str(np.argmax(i)))
                if text:
                    text_list.append(text)
            text = ''.join(text_list)
            for i in vector:
                recognition_rate = np.max(i) / np.sum(np.abs(i))
                recognition_rate_liat.append(recognition_rate)
            recognition_rate = self.recognition_probability(recognition_rate_liat)
            return text, recognition_rate
        elif self.mode == 'NUM_CLASSES':
            vector = vector[0]
            text = np.argmax(vector)
            text = num_classes.get(str(text))
            recognition_rate = np.max(vector) / np.sum(np.abs(vector))
            return text, recognition_rate
        elif self.mode == 'CTC':
            vector = vector[0]
            for i in vector:
                text = num_classes.get(str(np.argmax(i)))
                if text:
                    text_list.append(text)
            text = ''.join(text_list)
            for i in vector:
                recognition_rate = np.max(i) / np.sum(np.abs(i))
                recognition_rate_liat.append(recognition_rate)
            recognition_rate = self.recognition_probability(recognition_rate_liat)
            return text, recognition_rate
        else:
            raise ValueError(f'还没写{{self.mode}}这种预测方法')

    def predict_image(self):
        global right_value
        global predicted_value
        start_time = time.time()
        model = self.model
        vertor = model.predict(self.decode_image(self.image))
        text, recognition_rate = self.decode_vector(vector=vertor, num_classes=self.num_classes)
        right_text = self.decode_label()
        logger.info(f'预测为{{text}},真实为{{right_text}}')
        logger.info(f'识别率为:{{recognition_rate * 100}}%')
        if str(text) != str(right_text):
            logger.error(f'预测失败的图片路径为:{{self.image}}')
            right_value = right_value + 1
            logger.info(f'正确率:{{(predicted_value / right_value) * 100}}%')
            if predicted_value > 0:
                logger.info(f'预测正确{{predicted_value}}张图片')
        else:
            predicted_value = predicted_value + 1
            right_value = right_value + 1
            logger.info(f'正确率:{{(predicted_value / right_value) * 100}}%')
            if predicted_value > 0:
                logger.info(f'预测正确{{predicted_value}}张图片')
        end_time = time.time()
        logger.info(f'已识别{{right_value}}张图片')
        logger.info(f'识别时间为{{end_time - start_time}}s')

    def api(self):
        start_time = time.time()
        image = base64.b64decode(self.image)
        model = self.model
        vertor = model.predict(self.decode_image(image=image))
        result, recognition_rate = self.decode_vector(vector=vertor, num_classes=self.num_classes)
        end_time = time.time()
        times = end_time - start_time
        return (result, recognition_rate, times)


def cheak_path(path):
    number = 0
    while True:
        if os.path.exists(path):
            paths, name = os.path.split(path)
            name, mix = os.path.splitext(name)
            number = number + 1
            name = re.split('_', name)[0]
            logger.debug(name)
            name = name + f'_V{{number}}.0'
            path = os.path.join(paths, name + mix)
            return path
        if not os.path.exists(path):
            return path

"""


def gen_sample_by_captcha(work_path, project_name):
    return f"""# -*- coding: UTF-8 -*-
import os
import time
import json
import random
from tqdm import tqdm
from captcha.image import ImageCaptcha
from concurrent.futures import ThreadPoolExecutor


def gen_special_img(text, file_path, width, height):
    # 生成img文件
    generator = ImageCaptcha(width=width, height=height)  # 指定大小
    img = generator.generate_image(text)  # 生成图片
    img.save(file_path)  # 保存图片


def gen_ima_by_batch(root_dir, image_suffix, characters, count, char_count, width, height):
    # 判断文件夹是否存在
    if not os.path.exists(root_dir):
        os.makedirs(root_dir)

    for _ in tqdm(enumerate(range(count)), desc='Generate captcha image'):
        text = ""
        for _ in range(random.choice(char_count)):
            text += random.choice(characters)

        timec = str(time.time()).replace(".", "")
        p = os.path.join(root_dir, "{{}}_{{}}.{{}}".format(text, timec, image_suffix))
        gen_special_img(text, p, width, height)

        # logger.debug("Generate captcha image => {{}}".format(index + 1))


def main():
    with open("captcha_config.json", "r") as f:
        config = json.load(f)
    # 配置参数
    train_dir = config["train_dir"]
    validation_dir = config["validation_dir"]
    test_dir = config["test_dir"]
    image_suffix = config["image_suffix"]  # 图片储存后缀
    characters = config["characters"]  # 图片上显示的字符集 # characters = "0123456789abcdefghijklmnopqrstuvwxyz"
    count = config["count"]  # 生成多少张样本
    char_count = config["char_count"]  # 图片上的字符数量

    # 设置图片高度和宽度
    width = config["width"]
    height = config["height"]

    with ThreadPoolExecutor(max_workers=3) as t:
        t.submit(gen_ima_by_batch, train_dir, image_suffix, characters, count, char_count, width, height)
        t.submit(gen_ima_by_batch, validation_dir, image_suffix, characters, count, char_count, width, height)
        t.submit(gen_ima_by_batch, test_dir, image_suffix, characters, count, char_count, width, height)


if __name__ == '__main__':
    main()

"""


def init_working_space(work_path, project_name):
    return f"""# 检查项目路径
import os
import shutil
from loguru import logger
from {work_path}.{project_name}.settings import label_path
from {work_path}.{project_name}.settings import App_model_path
from {work_path}.{project_name}.settings import checkpoint_path


def chrak_path():
    path = os.getcwd()
    paths = ['test_dataset', 'train_dataset', 'validation_dataset', 'train_enhance_dataset', 'train_pack_dataset',
             'validation_pack_dataset', 'test_pack_dataset', 'model', 'logs', 'CSVLogger', checkpoint_path,
             label_path, App_model_path]
    for i in paths:
        mix = os.path.join(path, i)
        if not os.path.exists(mix):
            os.mkdir(mix)


def del_file():
    path = [os.path.join(os.getcwd(), 'CSVLogger'),
            os.path.join(os.getcwd(), 'logs'), checkpoint_path]
    for i in path:
        try:
            shutil.rmtree(i)
        except Exception as e:
            logger.error(e)


if __name__ == '__main__':
    del_file()
    chrak_path()
"""


def models(work_path, project_name):
    return f"""import math
import json
import tensorflow as tf
from plot_model import plot_model
from {work_path}.{project_name}.settings import LR
from {work_path}.{project_name}.settings import n_class_file
from {work_path}.{project_name}.settings import IMAGE_HEIGHT
from {work_path}.{project_name}.settings import IMAGE_WIDTH
from {work_path}.{project_name}.settings import CAPTCHA_LENGTH
from {work_path}.{project_name}.settings import IMAGE_CHANNALS

inputs_shape = (IMAGE_HEIGHT, IMAGE_WIDTH, IMAGE_CHANNALS)


class DropBlock(tf.keras.layers.Layer):
    # drop機率、block size
    def __init__(self, drop_rate=0.2, block_size=3, **kwargs):
        super(DropBlock, self).__init__(**kwargs)
        self.rate = drop_rate
        self.block_size = block_size

    def call(self, inputs, training=None):
        # if training:
        '''
        feature map mask tensor
        創建一個均勻取樣的Tensor，加上drop rate之後取整數，則為1的部份表示drop block的中心點
        經由maxpooling將中心點擴散成block size大小
        最後將Tensor值更改(0->1, 1->0)
        則可形成mask
        '''
        # batch size
        b = tf.shape(inputs)[0]

        random_tensor = tf.random.uniform(shape=[b, self.m_h, self.m_w, self.c]) + self.bernoulli_rate
        binary_tensor = tf.floor(random_tensor)
        binary_tensor = tf.pad(binary_tensor, [[0, 0],
                                               [self.block_size // 2, self.block_size // 2],
                                               [self.block_size // 2, self.block_size // 2],
                                               [0, 0]])
        binary_tensor = tf.nn.max_pool(binary_tensor,
                                       [1, self.block_size, self.block_size, 1],
                                       [1, 1, 1, 1],
                                       'SAME')
        binary_tensor = 1 - binary_tensor
        inputs = tf.math.divide(inputs, (1 - self.rate)) * binary_tensor
        return inputs

    def get_config(self):
        config = super(DropBlock, self).get_config()
        return config

    def build(self, input_shape):
        # feature map size (height, weight, channel)
        self.b, self.h, self.w, self.c = input_shape.as_list()
        # mask h, w
        self.m_h = self.h - (self.block_size // 2) * 2
        self.m_w = self.w - (self.block_size // 2) * 2
        self.bernoulli_rate = (self.rate * self.h * self.w) / (self.m_h * self.m_w * self.block_size ** 2)


# inception
class Inception(object):
    @staticmethod
    def BasicConv2D(inputs, filters, kernel_size, strides, padding, training=None, **kwargs):
        x = tf.keras.layers.Conv2D(filters=filters,
                                   kernel_size=kernel_size,
                                   strides=strides,
                                   padding=padding, kernel_initializer=tf.keras.initializers.he_normal())(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training)
        x = tf.nn.swish(x)
        return x

    @staticmethod
    def Conv2DLinear(inputs, filters, kernel_size, strides, padding, training=None, **kwargs):
        x = tf.keras.layers.Conv2D(filters=filters,
                                   kernel_size=kernel_size,
                                   strides=strides,
                                   padding=padding, kernel_initializer=tf.keras.initializers.he_normal())(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training)
        return x

    @staticmethod
    def Stem(inputs, training=None, **kwargs):
        x = Inception.BasicConv2D(inputs, filters=32,
                                  kernel_size=(3, 3),
                                  strides=2,
                                  padding='same', training=training)
        x = Inception.BasicConv2D(x, filters=32,
                                  kernel_size=(3, 3),
                                  strides=1,
                                  padding='same', training=training)
        x = Inception.BasicConv2D(x, filters=64,
                                  kernel_size=(3, 3),
                                  strides=1,
                                  padding='same', training=training)
        branch_1 = tf.keras.layers.MaxPool2D(pool_size=(3, 3),
                                             strides=2,
                                             padding="same")(x)
        branch_2 = Inception.BasicConv2D(x, filters=96,
                                         kernel_size=(3, 3),
                                         strides=2,
                                         padding="same", training=training)
        x = tf.concat(values=[branch_1, branch_2], axis=-1)
        branch_3 = Inception.BasicConv2D(x, filters=64,
                                         kernel_size=(1, 1),
                                         strides=1,
                                         padding="same", training=training)
        branch_3 = Inception.BasicConv2D(branch_3, filters=96,
                                         kernel_size=(3, 3),
                                         strides=1,
                                         padding="same", training=training)
        branch_4 = Inception.BasicConv2D(x, filters=64,
                                         kernel_size=(1, 1),
                                         strides=1,
                                         padding="same", training=training)
        branch_4 = Inception.BasicConv2D(branch_4, filters=64,
                                         kernel_size=(7, 1),
                                         strides=1,
                                         padding="same", training=training)
        branch_4 = Inception.BasicConv2D(branch_4, filters=64,
                                         kernel_size=(1, 7),
                                         strides=1,
                                         padding="same", training=training)
        branch_4 = Inception.BasicConv2D(branch_4, filters=96,
                                         kernel_size=(3, 3),
                                         strides=1,
                                         padding="same", training=training)
        x = tf.concat(values=[branch_3, branch_4], axis=-1)
        branch_5 = Inception.BasicConv2D(x, filters=192,
                                         kernel_size=(3, 3),
                                         strides=2,
                                         padding="same", training=training)
        branch_6 = tf.keras.layers.MaxPool2D(pool_size=(3, 3),
                                             strides=2,
                                             padding="same")(x)
        return tf.concat(values=[branch_5, branch_6], axis=-1)

    @staticmethod
    def ReductionA(inputs, k, l, m, n, training=None, **kwargs):
        b1 = tf.keras.layers.MaxPool2D(pool_size=(3, 3),
                                       strides=2,
                                       padding="same")(inputs)
        b2 = Inception.BasicConv2D(inputs, filters=n,
                                   kernel_size=(3, 3),
                                   strides=2,
                                   padding="same", training=training)
        b3 = Inception.BasicConv2D(inputs, filters=k,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", training=training)
        b3 = Inception.BasicConv2D(b3, filters=l,
                                   kernel_size=(3, 3),
                                   strides=1,
                                   padding="same", training=training)
        b3 = Inception.BasicConv2D(b3, filters=m,
                                   kernel_size=(3, 3),
                                   strides=2,
                                   padding="same", training=training)
        return tf.concat(values=[b1, b2, b3], axis=-1)

    @staticmethod
    def InceptionResNetA(inputs, training=None, **kwargs):
        b1 = Inception.BasicConv2D(inputs, filters=32,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", training=training)
        b2 = Inception.BasicConv2D(inputs, filters=32,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", training=training)
        b2 = Inception.BasicConv2D(b2, filters=32,
                                   kernel_size=(3, 3),
                                   strides=1,
                                   padding="same", training=training)
        b3 = Inception.BasicConv2D(inputs, filters=32,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", training=training)
        b3 = Inception.BasicConv2D(b3, filters=48,
                                   kernel_size=(3, 3),
                                   strides=1,
                                   padding="same", training=training)
        b3 = Inception.BasicConv2D(b3, filters=64,
                                   kernel_size=(3, 3),
                                   strides=1,
                                   padding="same", training=training)
        x = tf.concat(values=[b1, b2, b3], axis=-1)
        x = Inception.Conv2DLinear(x, filters=384,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", training=training)
        output = tf.keras.layers.add([x, inputs])
        return tf.nn.swish(output)

    @staticmethod
    def InceptionResNetB(inputs, training=None, **kwargs):
        b1 = Inception.BasicConv2D(inputs, filters=192,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", training=training)
        b2 = Inception.BasicConv2D(inputs, filters=128,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", training=training)
        b2 = Inception.BasicConv2D(b2, filters=160,
                                   kernel_size=(1, 7),
                                   strides=1,
                                   padding="same", training=training)
        b2 = Inception.BasicConv2D(b2, filters=192,
                                   kernel_size=(7, 1),
                                   strides=1,
                                   padding="same", training=training)
        x = tf.concat(values=[b1, b2], axis=-1)
        x = Inception.Conv2DLinear(x, filters=1152,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", training=training)
        output = tf.keras.layers.add([x, inputs])
        return tf.nn.swish(output)

    @staticmethod
    def InceptionResNetC(inputs, training=None, **kwargs):
        b1 = Inception.BasicConv2D(inputs, filters=192,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", training=training)
        b2 = Inception.BasicConv2D(inputs, filters=192,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", training=training)
        b2 = Inception.BasicConv2D(b2, filters=224,
                                   kernel_size=(1, 3),
                                   strides=1,
                                   padding="same", training=training)
        b2 = Inception.BasicConv2D(b2, filters=256,
                                   kernel_size=(3, 1),
                                   strides=1,
                                   padding="same", training=training)
        x = tf.concat(values=[b1, b2], axis=-1)
        x = Inception.Conv2DLinear(x, filters=2144,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", training=training)
        output = tf.keras.layers.add([x, inputs])
        return tf.nn.swish(output)

    @staticmethod
    def ReductionB(inputs, training=None, **kwargs):
        b1 = tf.keras.layers.MaxPool2D(pool_size=(3, 3),
                                       strides=2,
                                       padding="same")(inputs)
        b2 = Inception.BasicConv2D(inputs, filters=256,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", training=training)
        b2 = Inception.BasicConv2D(b2, filters=384,
                                   kernel_size=(3, 3),
                                   strides=2,
                                   padding="same", training=training)
        b3 = Inception.BasicConv2D(inputs, filters=256,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", training=training)
        b3 = Inception.BasicConv2D(b3, filters=288,
                                   kernel_size=(3, 3),
                                   strides=2,
                                   padding="same", training=training)
        b4 = Inception.BasicConv2D(inputs, filters=256,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", training=training)
        b4 = Inception.BasicConv2D(b4, filters=288,
                                   kernel_size=(3, 3),
                                   strides=1,
                                   padding="same", training=training)
        b4 = Inception.BasicConv2D(b4, filters=320,
                                   kernel_size=(3, 3),
                                   strides=2,
                                   padding="same", training=training)
        return tf.concat(values=[b1, b2, b3, b4], axis=-1)

    @staticmethod
    def build_inception_resnet_a(x, n):
        for _ in range(n):
            x = Inception.InceptionResNetA(x)
        return x

    @staticmethod
    def build_inception_resnet_b(x, n):
        for _ in range(n):
            x = Inception.InceptionResNetB(x)
        return x

    @staticmethod
    def build_inception_resnet_c(x, n):
        for _ in range(n):
            x = Inception.InceptionResNetC(x)
        return x

    @staticmethod
    def InceptionResNetV2(training=None, mask=None):
        inputs = tf.keras.layers.Input(shape=inputs_shape)
        x = Inception.Stem(inputs)
        x = Inception.build_inception_resnet_a(x, 5)
        x = Inception.ReductionA(x, k=256, l=256, m=384, n=384)
        x = Inception.build_inception_resnet_b(x, 10)
        x = Inception.ReductionB(x)
        x = Inception.build_inception_resnet_c(x, 5)
        x = tf.keras.layers.AveragePooling2D(pool_size=(2, 2))(x)
        x = tf.keras.layers.Dropout(rate=0.2)(x)
        x = tf.keras.layers.Flatten()(x)
        outputs = tf.keras.layers.Dense(units=CAPTCHA_LENGTH * Settings.settings(),
                                        activation=tf.keras.activations.softmax)(x)
        outputs = tf.keras.layers.Reshape((CAPTCHA_LENGTH, Settings.settings()))(outputs)
        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        return model


# densenet
class Densenet(object):

    @staticmethod
    def densenet_bottleneck(inputs, growth_rate, drop_rate, training=None, **kwargs):
        x = tf.keras.layers.BatchNormalization()(inputs, training=training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.Conv2D(filters=4 * growth_rate,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", kernel_initializer=tf.keras.initializers.he_normal())(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.Conv2D(filters=growth_rate,
                                   kernel_size=(3, 3),
                                   strides=1,
                                   padding="same", kernel_initializer=tf.keras.initializers.he_normal())(x)
        # x = tf.keras.layers.Dropout(rate=drop_rate)(x)
        # x = tf.keras.layers.GaussianDropout(rate=drop_rate)(x)
        x = tf.keras.layers.GaussianNoise(stddev=drop_rate)(x)
        # x = DropBlock(drop_rate=drop_rate)(x)
        return x

    @staticmethod
    def densenet_denseblock(inputs, num_layers, growth_rate, drop_rate, training=None, **kwargs):
        features_list = []
        features_list.append(inputs)
        x = inputs
        for _ in range(num_layers):
            y = Densenet.densenet_bottleneck(x, growth_rate=growth_rate, drop_rate=drop_rate, training=training)
            features_list.append(y)
            x = tf.concat(features_list, axis=-1)
        features_list.clear()
        return x

    @staticmethod
    def densenet_transitionlayer(inputs, out_channels, training=None, **kwargs):
        x = tf.keras.layers.BatchNormalization()(inputs, training=training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.Conv2D(filters=out_channels,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", kernel_initializer=tf.keras.initializers.he_normal())(x)
        x = tf.keras.layers.MaxPool2D(pool_size=(2, 2),
                                      strides=2,
                                      padding="same")(x)
        return x

    @staticmethod
    def Densenet(num_init_features, growth_rate, block_layers, compression_rate, drop_rate, training=None, mask=None):
        inputs = tf.keras.layers.Input(shape=inputs_shape)
        x = tf.keras.layers.Conv2D(filters=num_init_features,
                                   kernel_size=(7, 7),
                                   strides=2,
                                   padding="same", kernel_initializer=tf.keras.initializers.he_normal())(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.MaxPool2D(pool_size=(3, 3),
                                      strides=2,
                                      padding="same")(x)
        num_channels = num_init_features
        x = Densenet.densenet_denseblock(x, num_layers=block_layers[0], growth_rate=growth_rate, drop_rate=drop_rate)
        num_channels += growth_rate * block_layers[0]

        num_channels = compression_rate * num_channels
        x = Densenet.densenet_transitionlayer(x, out_channels=int(num_channels))
        x = Densenet.densenet_denseblock(x, num_layers=block_layers[1], growth_rate=growth_rate, drop_rate=drop_rate)
        num_channels += growth_rate * block_layers[1]
        num_channels = compression_rate * num_channels
        x = Densenet.densenet_transitionlayer(x, out_channels=int(num_channels))
        x = Densenet.densenet_denseblock(x, num_layers=block_layers[2], growth_rate=growth_rate, drop_rate=drop_rate)
        num_channels += growth_rate * block_layers[2]
        num_channels = compression_rate * num_channels
        x = Densenet.densenet_transitionlayer(x, out_channels=int(num_channels))
        x = Densenet.densenet_denseblock(x, num_layers=block_layers[3], growth_rate=growth_rate, drop_rate=drop_rate)
        x = tf.keras.layers.GlobalAveragePooling2D()(x)
        outputs = tf.keras.layers.Dense(units=CAPTCHA_LENGTH * Settings.settings(),
                                        activation=tf.keras.activations.softmax)(x)
        outputs = tf.keras.layers.Reshape((CAPTCHA_LENGTH, Settings.settings()))(outputs)
        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        return model

    @staticmethod
    def Densenet_num_classes(num_init_features, growth_rate, block_layers, compression_rate, drop_rate, training=None,
                             mask=None):
        inputs = tf.keras.layers.Input(shape=inputs_shape)
        x = tf.keras.layers.Conv2D(filters=num_init_features,
                                   kernel_size=(7, 7),
                                   strides=2,
                                   padding="same", kernel_initializer=tf.keras.initializers.he_normal())(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.MaxPool2D(pool_size=(3, 3),
                                      strides=2,
                                      padding="same")(x)
        num_channels = num_init_features
        x = Densenet.densenet_denseblock(x, num_layers=block_layers[0], growth_rate=growth_rate, drop_rate=drop_rate)
        num_channels += growth_rate * block_layers[0]
        num_channels = compression_rate * num_channels
        x = Densenet.densenet_transitionlayer(x, out_channels=int(num_channels))
        x = Densenet.densenet_denseblock(x, num_layers=block_layers[1], growth_rate=growth_rate, drop_rate=drop_rate)
        num_channels += growth_rate * block_layers[1]
        num_channels = compression_rate * num_channels
        x = Densenet.densenet_transitionlayer(x, out_channels=int(num_channels))
        x = Densenet.densenet_denseblock(x, num_layers=block_layers[2], growth_rate=growth_rate, drop_rate=drop_rate)
        num_channels += growth_rate * block_layers[2]
        num_channels = compression_rate * num_channels
        x = Densenet.densenet_transitionlayer(x, out_channels=int(num_channels))
        x = Densenet.densenet_denseblock(x, num_layers=block_layers[3], growth_rate=growth_rate, drop_rate=drop_rate)
        x = tf.keras.layers.GlobalAveragePooling2D()(x)
        outputs = tf.keras.layers.Dense(units=Settings.settings_num_classes(), activation=tf.keras.activations.softmax)(
            x)
        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        return model


# efficientnet
class Efficientnet(object):

    @staticmethod
    def round_filters(filters, multiplier):
        depth_divisor = 8
        min_depth = None
        min_depth = min_depth or depth_divisor
        filters = filters * multiplier
        new_filters = max(min_depth, int(filters + depth_divisor / 2) // depth_divisor * depth_divisor)
        if new_filters < 0.9 * filters:
            new_filters += depth_divisor
        return int(new_filters)

    @staticmethod
    def round_repeats(repeats, multiplier):
        if not multiplier:
            return repeats
        return int(math.ceil(multiplier * repeats))

    @staticmethod
    def efficientnet_seblock(inputs, input_channels, ratio=0.25, **kwargs):
        num_reduced_filters = max(1, int(input_channels * ratio))
        x = tf.keras.layers.GlobalAveragePooling2D()(inputs)
        x = tf.expand_dims(input=x, axis=1)
        x = tf.expand_dims(input=x, axis=1)
        x = tf.keras.layers.Conv2D(filters=num_reduced_filters, kernel_size=(1, 1), strides=1, padding='same',
                                   kernel_initializer=tf.keras.initializers.he_normal())(x)
        x = tf.nn.swish(x)
        x = tf.keras.layers.Conv2D(filters=input_channels, kernel_size=(1, 1), strides=1, padding='same',
                                   kernel_initializer=tf.keras.initializers.he_normal())(x)
        x = tf.nn.sigmoid(x)
        x = inputs * x
        return x

    @staticmethod
    def efficientnet_mbconv(inputs, in_channels, out_channels, expansion_factor, stride, k, drop_connect_rate,
                            training=None, **kwargs):
        x = tf.keras.layers.Conv2D(filters=in_channels * expansion_factor,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same",
                                   use_bias=False, kernel_initializer=tf.keras.initializers.he_normal())(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.DepthwiseConv2D(kernel_size=(k, k),
                                            strides=stride,
                                            padding="same",
                                            use_bias=False, kernel_initializer=tf.keras.initializers.he_normal())(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = Efficientnet.efficientnet_seblock(x, input_channels=in_channels * expansion_factor)
        x = tf.keras.layers.Conv2D(filters=in_channels * expansion_factor,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same",
                                   use_bias=False, kernel_initializer=tf.keras.initializers.he_normal())(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        if stride == 1 and in_channels == out_channels:
            if drop_connect_rate:
                x = tf.keras.layers.Dropout(rate=drop_connect_rate)(x)
            x = tf.keras.layers.concatenate([x, inputs])
        return x

    @staticmethod
    def efficientnet_build_mbconv_block(x, in_channels, out_channels, layers, stride, expansion_factor, k,
                                        drop_connect_rate):
        for i in range(layers):
            if i == 0:
                x = Efficientnet.efficientnet_mbconv(x, in_channels=in_channels,
                                                     out_channels=out_channels,
                                                     expansion_factor=expansion_factor,
                                                     stride=stride,
                                                     k=k,
                                                     drop_connect_rate=drop_connect_rate)
            else:
                x = Efficientnet.efficientnet_mbconv(x, in_channels=out_channels,
                                                     out_channels=out_channels,
                                                     expansion_factor=expansion_factor,
                                                     stride=1,
                                                     k=k,
                                                     drop_connect_rate=drop_connect_rate)
        return x

    @staticmethod
    def Efficientnet(width_coefficient, depth_coefficient, dropout_rate, drop_connect_rate=0.2, training=None,
                     mask=None):
        inputs = tf.keras.layers.Input(shape=inputs_shape)
        x = tf.keras.layers.Conv2D(filters=Efficientnet.round_filters(32, width_coefficient),
                                   kernel_size=(3, 3),
                                   strides=2,
                                   padding="same",
                                   use_bias=False)(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.swish(x)
        x = Efficientnet.efficientnet_build_mbconv_block(x,
                                                         in_channels=Efficientnet.round_filters(32, width_coefficient),
                                                         out_channels=Efficientnet.round_filters(16, width_coefficient),
                                                         layers=Efficientnet.round_repeats(1, depth_coefficient),
                                                         stride=1,
                                                         expansion_factor=1, k=3, drop_connect_rate=drop_connect_rate)
        x = Efficientnet.efficientnet_build_mbconv_block(x,
                                                         in_channels=Efficientnet.round_filters(16, width_coefficient),
                                                         out_channels=Efficientnet.round_filters(24, width_coefficient),
                                                         layers=Efficientnet.round_repeats(2, depth_coefficient),
                                                         stride=2,
                                                         expansion_factor=6, k=3, drop_connect_rate=drop_connect_rate)
        x = Efficientnet.efficientnet_build_mbconv_block(x,
                                                         in_channels=Efficientnet.round_filters(24, width_coefficient),
                                                         out_channels=Efficientnet.round_filters(40, width_coefficient),
                                                         layers=Efficientnet.round_repeats(2, depth_coefficient),
                                                         stride=2,
                                                         expansion_factor=6, k=5, drop_connect_rate=drop_connect_rate)
        x = Efficientnet.efficientnet_build_mbconv_block(x,
                                                         in_channels=Efficientnet.round_filters(40, width_coefficient),
                                                         out_channels=Efficientnet.round_filters(80, width_coefficient),
                                                         layers=Efficientnet.round_repeats(3, depth_coefficient),
                                                         stride=2,
                                                         expansion_factor=6, k=3, drop_connect_rate=drop_connect_rate)
        x = Efficientnet.efficientnet_build_mbconv_block(x,
                                                         in_channels=Efficientnet.round_filters(80, width_coefficient),
                                                         out_channels=Efficientnet.round_filters(112,
                                                                                                 width_coefficient),
                                                         layers=Efficientnet.round_repeats(3, depth_coefficient),
                                                         stride=1,
                                                         expansion_factor=6, k=5, drop_connect_rate=drop_connect_rate)
        x = Efficientnet.efficientnet_build_mbconv_block(x,
                                                         in_channels=Efficientnet.round_filters(112, width_coefficient),
                                                         out_channels=Efficientnet.round_filters(192,
                                                                                                 width_coefficient),
                                                         layers=Efficientnet.round_repeats(4, depth_coefficient),
                                                         stride=2,
                                                         expansion_factor=6, k=5, drop_connect_rate=drop_connect_rate)
        x = Efficientnet.efficientnet_build_mbconv_block(x,
                                                         in_channels=Efficientnet.round_filters(192, width_coefficient),
                                                         out_channels=Efficientnet.round_filters(320,
                                                                                                 width_coefficient),
                                                         layers=Efficientnet.round_repeats(1, depth_coefficient),
                                                         stride=1,
                                                         expansion_factor=6, k=3, drop_connect_rate=drop_connect_rate)
        x = tf.keras.layers.Conv2D(filters=Efficientnet.round_filters(1280, width_coefficient),
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same",
                                   use_bias=False, kernel_initializer=tf.keras.initializers.he_normal())(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.GlobalAveragePooling2D()(x)
        x = tf.keras.layers.Dropout(rate=dropout_rate)(x)
        outputs = tf.keras.layers.Dense(units=CAPTCHA_LENGTH * Settings.settings(),
                                        activation=tf.keras.activations.softmax)(x)
        outputs = tf.keras.layers.Reshape((CAPTCHA_LENGTH, Settings.settings()))(outputs)
        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        return model


# mobilenet
class Mobilenet(object):
    @staticmethod
    def bottleneck(inputs, input_channels, output_channels, expansion_factor, stride, training=None, **kwargs):
        x = tf.keras.layers.Conv2D(filters=input_channels * expansion_factor,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same")(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.relu6(x)
        x = tf.keras.layers.DepthwiseConv2D(kernel_size=(3, 3),
                                            strides=stride,
                                            padding="same")(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.relu6(x)
        x = tf.keras.layers.Conv2D(filters=output_channels,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same")(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.keras.layers.Activation(tf.keras.activations.linear)(x)
        if stride == 1 and input_channels == output_channels:
            x = tf.keras.layers.concatenate([x, inputs])
        return x

    @staticmethod
    def build_bottleneck(inputs, t, in_channel_num, out_channel_num, n, s):
        bottleneck = inputs
        for i in range(n):
            if i == 0:
                bottleneck = Mobilenet.bottleneck(inputs, input_channels=in_channel_num,
                                                  output_channels=out_channel_num,
                                                  expansion_factor=t,
                                                  stride=s)
            else:
                bottleneck = Mobilenet.bottleneck(inputs, input_channels=out_channel_num,
                                                  output_channels=out_channel_num,
                                                  expansion_factor=t,
                                                  stride=1)
        return bottleneck

    @staticmethod
    def h_sigmoid(x):
        return tf.nn.relu6(x + 3) / 6

    @staticmethod
    def seblock(inputs, input_channels, r=16, **kwargs):
        x = tf.keras.layers.GlobalAveragePooling2D()(inputs)
        x = tf.keras.layers.Dense(units=input_channels // r)(x)
        x = tf.nn.swish(x)
        x = tf.keras.layers.Dense(units=input_channels)(x)
        x = Mobilenet.h_sigmoid(x)
        x = tf.expand_dims(x, axis=1)
        x = tf.expand_dims(x, axis=1)
        output = inputs * x
        return output

    @staticmethod
    def BottleNeck(inputs, in_size, exp_size, out_size, s, is_se_existing, NL, k, training=None, **kwargs):
        x = tf.keras.layers.Conv2D(filters=exp_size,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", kernel_initializer=tf.keras.initializers.he_normal())(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        if NL == 'HS':
            x = Mobilenet.h_swish(x)
        elif NL == 'RE':
            x = tf.nn.relu6(x)
        x = tf.keras.layers.DepthwiseConv2D(kernel_size=(k, k),
                                            strides=s,
                                            padding="same", kernel_initializer=tf.keras.initializers.he_normal())(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        if NL == 'HS':
            x = Mobilenet.h_swish(x)
        elif NL == 'RE':
            x = tf.nn.relu6(x)
        if is_se_existing:
            x = Mobilenet.seblock(x, input_channels=exp_size)
        x = tf.keras.layers.Conv2D(filters=out_size,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", kernel_initializer=tf.keras.initializers.he_normal())(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.keras.layers.Activation(tf.keras.activations.linear)(x)
        if s == 1 and in_size == out_size:
            x = tf.keras.layers.add([x, inputs])
        return x

    @staticmethod
    def h_swish(x):
        return x * Mobilenet.h_sigmoid(x)

    @staticmethod
    def MobileNetV1(training=None, mask=None):
        inputs = tf.keras.layers.Input(shape=inputs_shape)
        x = tf.keras.layers.Conv2D(filters=32,
                                   kernel_size=(3, 3),
                                   strides=2,
                                   padding="same")(inputs)
        x = tf.keras.layers.SeparableConv2D(filters=64,
                                            kernel_size=(3, 3),
                                            strides=1,
                                            padding="same")(x)
        x = tf.keras.layers.SeparableConv2D(filters=128,
                                            kernel_size=(3, 3),
                                            strides=2,
                                            padding="same")(x)
        x = tf.keras.layers.SeparableConv2D(filters=128,
                                            kernel_size=(3, 3),
                                            strides=1,
                                            padding="same")(x)
        x = tf.keras.layers.SeparableConv2D(filters=256,
                                            kernel_size=(3, 3),
                                            strides=2,
                                            padding="same")(x)
        x = tf.keras.layers.SeparableConv2D(filters=256,
                                            kernel_size=(3, 3),
                                            strides=1,
                                            padding="same")(x)
        x = tf.keras.layers.SeparableConv2D(filters=512,
                                            kernel_size=(3, 3),
                                            strides=2,
                                            padding="same")(x)
        x = tf.keras.layers.SeparableConv2D(filters=512,
                                            kernel_size=(3, 3),
                                            strides=1,
                                            padding="same")(x)
        x = tf.keras.layers.SeparableConv2D(filters=512,
                                            kernel_size=(3, 3),
                                            strides=1,
                                            padding="same")(x)
        x = tf.keras.layers.SeparableConv2D(filters=512,
                                            kernel_size=(3, 3),
                                            strides=1,
                                            padding="same")(x)
        x = tf.keras.layers.SeparableConv2D(filters=512,
                                            kernel_size=(3, 3),
                                            strides=1,
                                            padding="same")(x)
        x = tf.keras.layers.SeparableConv2D(filters=512,
                                            kernel_size=(3, 3),
                                            strides=1,
                                            padding="same")(x)
        x = tf.keras.layers.SeparableConv2D(filters=1024,
                                            kernel_size=(3, 3),
                                            strides=2,
                                            padding="same")(x)
        x = tf.keras.layers.SeparableConv2D(filters=1024,
                                            kernel_size=(3, 3),
                                            strides=1,
                                            padding="same")(x)
        x = tf.keras.layers.AveragePooling2D(pool_size=(7, 7),
                                             strides=1)(x)
        outputs = tf.keras.layers.Dense(units=Settings.settings(),
                                        activation=tf.keras.activations.softmax)(x)
        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        return model

    @staticmethod
    def MobileNetV2(training=None, mask=None):
        inputs = tf.keras.layers.Input(shape=inputs_shape)
        x = tf.keras.layers.Conv2D(filters=32,
                                   kernel_size=(3, 3),
                                   strides=2,
                                   padding="same")(inputs)
        x = Mobilenet.build_bottleneck(x, t=1,
                                       in_channel_num=32,
                                       out_channel_num=16,
                                       n=1,
                                       s=1)
        x = Mobilenet.build_bottleneck(x, t=6,
                                       in_channel_num=16,
                                       out_channel_num=24,
                                       n=2,
                                       s=2)
        x = Mobilenet.build_bottleneck(x, t=6,
                                       in_channel_num=24,
                                       out_channel_num=32,
                                       n=3,
                                       s=2)
        x = Mobilenet.build_bottleneck(x, t=6,
                                       in_channel_num=32,
                                       out_channel_num=64,
                                       n=4,
                                       s=2)
        x = Mobilenet.build_bottleneck(x, t=6,
                                       in_channel_num=64,
                                       out_channel_num=96,
                                       n=3,
                                       s=1)
        x = Mobilenet.build_bottleneck(x, t=6,
                                       in_channel_num=96,
                                       out_channel_num=160,
                                       n=3,
                                       s=2)
        x = Mobilenet.build_bottleneck(x, t=6,
                                       in_channel_num=160,
                                       out_channel_num=320,
                                       n=1,
                                       s=1)
        x = tf.keras.layers.Conv2D(filters=1280,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same")(x)
        x = tf.keras.layers.AveragePooling2D(pool_size=(7, 7))(x)
        outputs = tf.keras.layers.Conv2D(filters=Settings.settings(),
                                         kernel_size=(1, 1),
                                         strides=1,
                                         padding="same",
                                         activation=tf.keras.activations.softmax)(x)
        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        return model

    @staticmethod
    def MobileNetV3Large(training=None, mask=None):
        inputs = tf.keras.layers.Input(shape=inputs_shape)
        x = tf.keras.layers.Conv2D(filters=16,
                                   kernel_size=(3, 3),
                                   strides=2,
                                   padding="same", kernel_initializer=tf.keras.initializers.he_normal())(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = Mobilenet.h_swish(x)
        x = Mobilenet.BottleNeck(x, in_size=16, exp_size=16, out_size=16, s=1, is_se_existing=False, NL="RE", k=3,
                                 training=training)
        x = Mobilenet.BottleNeck(x, in_size=16, exp_size=64, out_size=24, s=2, is_se_existing=False, NL="RE", k=3,
                                 training=training)
        x = Mobilenet.BottleNeck(x, in_size=24, exp_size=72, out_size=24, s=1, is_se_existing=False, NL="RE", k=3,
                                 training=training)
        x = Mobilenet.BottleNeck(x, in_size=24, exp_size=72, out_size=40, s=2, is_se_existing=True, NL="RE", k=5,
                                 training=training)
        x = Mobilenet.BottleNeck(x, in_size=40, exp_size=120, out_size=40, s=1, is_se_existing=True, NL="RE", k=5,
                                 training=training)
        x = Mobilenet.BottleNeck(x, in_size=40, exp_size=120, out_size=40, s=1, is_se_existing=True, NL="RE", k=5,
                                 training=training)
        x = Mobilenet.BottleNeck(x, in_size=40, exp_size=240, out_size=80, s=2, is_se_existing=False, NL="HS", k=3,
                                 training=training)
        x = Mobilenet.BottleNeck(x, in_size=80, exp_size=200, out_size=80, s=1, is_se_existing=False, NL="HS", k=3,
                                 training=training)
        x = Mobilenet.BottleNeck(x, in_size=80, exp_size=184, out_size=80, s=1, is_se_existing=False, NL="HS", k=3,
                                 training=training)
        x = Mobilenet.BottleNeck(x, in_size=80, exp_size=184, out_size=80, s=1, is_se_existing=False, NL="HS", k=3,
                                 training=training)
        x = Mobilenet.BottleNeck(x, in_size=80, exp_size=480, out_size=112, s=1, is_se_existing=True, NL="HS", k=3,
                                 training=training)
        x = Mobilenet.BottleNeck(x, in_size=112, exp_size=672, out_size=112, s=1, is_se_existing=True, NL="HS", k=3,
                                 training=training)
        x = Mobilenet.BottleNeck(x, in_size=112, exp_size=672, out_size=160, s=2, is_se_existing=True, NL="HS", k=5,
                                 training=training)
        x = Mobilenet.BottleNeck(x, in_size=160, exp_size=960, out_size=160, s=1, is_se_existing=True, NL="HS", k=5,
                                 training=training)
        x = Mobilenet.BottleNeck(x, in_size=160, exp_size=960, out_size=160, s=1, is_se_existing=True, NL="HS", k=5,
                                 training=training)
        x = tf.keras.layers.Conv2D(filters=960,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", kernel_initializer=tf.keras.initializers.he_normal())(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = Mobilenet.h_swish(x)
        x = tf.keras.layers.AveragePooling2D(pool_size=(2, 2),
                                             strides=1)(x)
        x = tf.keras.layers.Conv2D(filters=1280,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same", kernel_initializer=tf.keras.initializers.he_normal())(x)
        x = Mobilenet.h_swish(x)
        outputs = tf.keras.layers.Conv2D(filters=Settings.settings(),
                                         kernel_size=(1, 1),
                                         strides=1,
                                         padding="same",
                                         activation=tf.keras.activations.softmax)(x)
        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        return model

    @staticmethod
    def MobileNetV3Small(training=None, mask=None):
        inputs = tf.keras.layers.Input(shape=inputs_shape)
        x = tf.keras.layers.Conv2D(filters=16,
                                   kernel_size=(3, 3),
                                   strides=2,
                                   padding="same")(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = Mobilenet.h_swish(x)
        x = Mobilenet.BottleNeck(x, in_size=16, exp_size=16, out_size=16, s=2, is_se_existing=True, NL="RE", k=3)
        x = Mobilenet.BottleNeck(x, in_size=16, exp_size=72, out_size=24, s=2, is_se_existing=False, NL="RE", k=3)
        x = Mobilenet.BottleNeck(x, in_size=24, exp_size=88, out_size=24, s=1, is_se_existing=False, NL="RE", k=3)
        x = Mobilenet.BottleNeck(x, in_size=24, exp_size=96, out_size=40, s=2, is_se_existing=True, NL="HS", k=5)
        x = Mobilenet.BottleNeck(x, in_size=40, exp_size=240, out_size=40, s=1, is_se_existing=True, NL="HS", k=5)
        x = Mobilenet.BottleNeck(x, in_size=40, exp_size=240, out_size=40, s=1, is_se_existing=True, NL="HS", k=5)
        x = Mobilenet.BottleNeck(x, in_size=40, exp_size=120, out_size=48, s=1, is_se_existing=True, NL="HS", k=5)
        x = Mobilenet.BottleNeck(x, in_size=48, exp_size=144, out_size=48, s=1, is_se_existing=True, NL="HS", k=5)
        x = Mobilenet.BottleNeck(x, in_size=48, exp_size=288, out_size=96, s=2, is_se_existing=True, NL="HS", k=5)
        x = Mobilenet.BottleNeck(x, in_size=96, exp_size=576, out_size=96, s=1, is_se_existing=True, NL="HS", k=5)
        x = Mobilenet.BottleNeck(x, in_size=96, exp_size=576, out_size=96, s=1, is_se_existing=True, NL="HS", k=5)
        x = tf.keras.layers.Conv2D(filters=576,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same")(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = Mobilenet.h_swish(x)
        x = tf.keras.layers.AveragePooling2D(pool_size=(2, 2),
                                             strides=1)(x)
        x = tf.keras.layers.Conv2D(filters=1280,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same")(x)
        outputs = tf.keras.layers.Conv2D(filters=CAPTCHA_LENGTH * Settings.settings(),
                                         kernel_size=(1, 1),
                                         strides=1,
                                         padding="same",
                                         activation=tf.keras.activations.softmax)(x)
        outputs = tf.keras.layers.Reshape((CAPTCHA_LENGTH, Settings.settings()))(outputs)
        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        return model


# resnext
class ResNeXt(object):
    @staticmethod
    def BasicBlock(inputs, filter_num, stride=1, training=None, **kwargs):
        if stride != 1:
            residual = tf.keras.layers.Conv2D(filters=filter_num,
                                              kernel_size=(1, 1),
                                              strides=stride)(inputs)
            residual = tf.keras.layers.BatchNormalization()(residual, training=training)
        else:
            residual = inputs

        x = tf.keras.layers.Conv2D(filters=filter_num,
                                   kernel_size=(3, 3),
                                   strides=stride,
                                   padding="same")(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.Conv2D(filters=filter_num,
                                   kernel_size=(3, 3),
                                   strides=1,
                                   padding="same")(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.swish(x)
        output = tf.keras.layers.concatenate([residual, x])
        return output

    @staticmethod
    def BottleNeck(inputs, filter_num, stride=1, training=None, **kwargs):
        residual = tf.keras.layers.Conv2D(filters=filter_num * 4,
                                          kernel_size=(1, 1),
                                          strides=stride, kernel_initializer=tf.keras.initializers.he_normal())(inputs)
        residual = tf.keras.layers.BatchNormalization()(residual, training=training)
        x = tf.keras.layers.Conv2D(filters=filter_num,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding='same', kernel_initializer=tf.keras.initializers.he_normal())(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.Conv2D(filters=filter_num,
                                   kernel_size=(3, 3),
                                   strides=stride,
                                   padding='same', kernel_initializer=tf.keras.initializers.he_normal())(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.Conv2D(filters=filter_num * 4,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding='same', kernel_initializer=tf.keras.initializers.he_normal())(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        return tf.nn.relu(tf.keras.layers.add([residual, x]))

    @staticmethod
    def make_basic_block_layer(inputs, filter_num, blocks, stride=1, training=None, mask=None):
        res_block = ResNeXt.BasicBlock(inputs, filter_num, stride=stride)
        for _ in range(1, blocks):
            res_block = ResNeXt.BasicBlock(inputs, filter_num, stride=1)
        return res_block

    @staticmethod
    def make_bottleneck_layer(inputs, filter_num, blocks, stride=1, training=None, mask=None):
        res_block = ResNeXt.BottleNeck(inputs, filter_num, stride=stride)
        for _ in range(1, blocks):
            res_block = ResNeXt.BottleNeck(inputs, filter_num, stride=1)
        return res_block

    @staticmethod
    def ResNeXt_BottleNeck(inputs, filters, strides, groups, training=None, **kwargs):
        x = tf.keras.layers.Conv2D(filters=filters,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same")(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.keras.layers.Conv2D(filters=filters,
                                   kernel_size=(3, 3),
                                   strides=strides,
                                   padding="same", )(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.relu(x)
        x = tf.keras.layers.Conv2D(filters=2 * filters,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same")(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        shortcut = tf.keras.layers.Conv2D(filters=2 * filters,
                                          kernel_size=(1, 1),
                                          strides=strides,
                                          padding="same")(inputs)
        shortcut = tf.keras.layers.BatchNormalization()(shortcut, training=training)
        output = tf.nn.relu(tf.keras.layers.add([x, shortcut]))
        return output

    @staticmethod
    def build_ResNeXt_block(inputs, filters, strides, groups, repeat_num):
        block = ResNeXt.ResNeXt_BottleNeck(inputs, filters=filters,
                                           strides=strides,
                                           groups=groups)
        for _ in range(1, repeat_num):
            block = ResNeXt.ResNeXt_BottleNeck(inputs, filters=filters,
                                               strides=1,
                                               groups=groups)
        return block

    @staticmethod
    def ResNetTypeI(layer_params, training=None, mask=None):
        inputs = tf.keras.layers.Input(shape=inputs_shape)
        x = tf.keras.layers.Conv2D(filters=64,
                                   kernel_size=(7, 7),
                                   strides=2,
                                   padding="same")(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.MaxPool2D(pool_size=(3, 3),
                                      strides=2,
                                      padding="same")(x)
        x = ResNeXt.make_basic_block_layer(x, filter_num=64,
                                           blocks=layer_params[0])
        x = ResNeXt.make_basic_block_layer(x, filter_num=128,
                                           blocks=layer_params[1],
                                           stride=2)
        x = ResNeXt.make_basic_block_layer(x, filter_num=256,
                                           blocks=layer_params[2],
                                           stride=2)
        x = ResNeXt.make_basic_block_layer(x, filter_num=512,
                                           blocks=layer_params[3],
                                           stride=2)
        x = tf.keras.layers.GlobalAveragePooling2D()(x)
        outputs = tf.keras.layers.Dense(units=CAPTCHA_LENGTH * Settings.settings(),
                                        activation=tf.keras.activations.softmax)(x)
        outputs = tf.keras.layers.Reshape((CAPTCHA_LENGTH, Settings.settings()))(outputs)
        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        return model

    @staticmethod
    def ResNetTypeII(layer_params, training=None, mask=None):
        inputs = tf.keras.layers.Input(shape=inputs_shape)
        x = tf.keras.layers.Conv2D(filters=64,
                                   kernel_size=(7, 7),
                                   strides=2,
                                   padding="same", kernel_initializer=tf.keras.initializers.he_normal())(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.MaxPool2D(pool_size=(3, 3),
                                      strides=2,
                                      padding="same")(x)
        x = ResNeXt.make_bottleneck_layer(x, filter_num=64,
                                          blocks=layer_params[0], training=training)
        x = ResNeXt.make_bottleneck_layer(x, filter_num=128,
                                          blocks=layer_params[1],
                                          stride=2, training=training)
        x = ResNeXt.make_bottleneck_layer(x, filter_num=256,
                                          blocks=layer_params[2],
                                          stride=2, training=training)
        x = ResNeXt.make_bottleneck_layer(x, filter_num=512,
                                          blocks=layer_params[3],
                                          stride=2, training=training)
        x = tf.keras.layers.GlobalAveragePooling2D()(x)
        outputs = tf.keras.layers.Dense(units=CAPTCHA_LENGTH * Settings.settings(),
                                        activation=tf.keras.activations.softmax)(x)
        outputs = tf.keras.layers.Reshape((CAPTCHA_LENGTH, Settings.settings()))(outputs)
        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        return model

    @staticmethod
    def Resnext(repeat_num_list, cardinality, training=None, mask=None):
        inputs = tf.keras.layers.Input(shape=inputs_shape)
        x = tf.keras.layers.Conv2D(filters=64,
                                   kernel_size=(7, 7),
                                   strides=2,
                                   padding="same")(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.relu(x)
        x = tf.keras.layers.MaxPool2D(pool_size=(3, 3),
                                      strides=2,
                                      padding="same")(x)
        x = ResNeXt.build_ResNeXt_block(x, filters=128,
                                        strides=1,
                                        groups=cardinality,
                                        repeat_num=repeat_num_list[0])
        x = ResNeXt.build_ResNeXt_block(x, filters=256,
                                        strides=2,
                                        groups=cardinality,
                                        repeat_num=repeat_num_list[1])
        x = ResNeXt.build_ResNeXt_block(x, filters=512,
                                        strides=2,
                                        groups=cardinality,
                                        repeat_num=repeat_num_list[2])
        x = ResNeXt.build_ResNeXt_block(x, filters=1024,
                                        strides=2,
                                        groups=cardinality,
                                        repeat_num=repeat_num_list[3])
        x = tf.keras.layers.GlobalAveragePooling2D()(x)
        outputs = tf.keras.layers.Dense(units=Settings.settings(), activation=tf.keras.activations.softmax)(x)
        outputs = tf.keras.layers.Reshape((CAPTCHA_LENGTH, Settings.settings()))(outputs)
        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        return model


# SEResNet
class SEResNet(object):
    @staticmethod
    def seblock(inputs, input_channels, r=16, **kwargs):
        x = tf.keras.layers.GlobalAveragePooling2D()(inputs)
        x = tf.keras.layers.Dense(units=input_channels // r)(x)
        x = tf.nn.swish(x)
        x = tf.keras.layers.Dense(units=input_channels)(x)
        x = tf.nn.sigmoid(x)
        x = tf.expand_dims(x, axis=1)
        x = tf.expand_dims(x, axis=1)
        output = tf.keras.layers.multiply(inputs=[inputs, x])
        return output

    @staticmethod
    def bottleneck(inputs, filter_num, stride=1, training=None):
        identity = tf.keras.layers.Conv2D(filters=filter_num * 4,
                                          kernel_size=(1, 1),
                                          strides=stride)(inputs)
        identity = tf.keras.layers.BatchNormalization()(identity)
        x = tf.keras.layers.Conv2D(filters=filter_num,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding='same')(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.Conv2D(filters=filter_num,
                                   kernel_size=(3, 3),
                                   strides=stride,
                                   padding='same')(x)
        x = tf.keras.layers.BatchNormalization()(x, training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.Conv2D(filters=filter_num * 4,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding='same')(x)
        x = tf.keras.layers.BatchNormalization()(x, training)
        x = SEResNet.seblock(x, input_channels=filter_num * 4)
        output = tf.nn.swish(tf.keras.layers.add([identity, x]))
        return output

    @staticmethod
    def _make_res_block(inputs, filter_num, blocks, stride=1):
        x = SEResNet.bottleneck(inputs, filter_num, stride=stride)
        for _ in range(1, blocks):
            x = SEResNet.bottleneck(x, filter_num, stride=1)
        return x

    @staticmethod
    def SEResNet(block_num, training=None, mask=None):
        inputs = tf.keras.layers.Input(shape=inputs_shape)
        x = tf.keras.layers.Conv2D(filters=64,
                                   kernel_size=(7, 7),
                                   strides=2,
                                   padding='same')(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training)
        x = tf.keras.layers.Activation(tf.keras.activations.swish)(x)
        x = tf.keras.layers.MaxPool2D(pool_size=(3, 3),
                                      strides=2)(x)
        x = SEResNet._make_res_block(x, filter_num=64,
                                     blocks=block_num[0])
        x = SEResNet._make_res_block(x, filter_num=128,
                                     blocks=block_num[1],
                                     stride=2)
        x = SEResNet._make_res_block(x, filter_num=256,
                                     blocks=block_num[2],
                                     stride=2)
        x = SEResNet._make_res_block(x, filter_num=512,
                                     blocks=block_num[3],
                                     stride=2)
        x = tf.keras.layers.GlobalAveragePooling2D()(x)
        outputs = tf.keras.layers.Dense(units=CAPTCHA_LENGTH * Settings.settings(),
                                        activation=tf.keras.activations.softmax)(x)
        outputs = tf.keras.layers.Reshape((CAPTCHA_LENGTH, Settings.settings()))(outputs)
        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        return model


# ShuffleNetV2
class ShuffleNetV2(object):
    @staticmethod
    def channel_shuffle(feature, group):
        channel_num = feature.shape[-1]
        if channel_num % group != 0:
            raise ValueError("The group must be divisible by the shape of the last dimension of the feature.")
        x = tf.reshape(feature, shape=(-1, feature.shape[1], feature.shape[2], group, channel_num // group))
        x = tf.transpose(x, perm=[0, 1, 2, 4, 3])
        x = tf.reshape(x, shape=(-1, feature.shape[1], feature.shape[2], channel_num))
        return x

    @staticmethod
    def ShuffleBlockS1(inputs, in_channels, out_channels, training=None, **kwargs):
        branch, x = tf.split(inputs, num_or_size_splits=2, axis=-1)
        x = tf.keras.layers.Conv2D(filters=out_channels // 2,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same")(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.DepthwiseConv2D(kernel_size=(3, 3), strides=1, padding="same")(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.keras.layers.Conv2D(filters=out_channels // 2,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same")(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.swish(x)
        outputs = tf.concat(values=[branch, x], axis=-1)
        outputs = ShuffleNetV2.channel_shuffle(feature=outputs, group=2)
        return outputs

    @staticmethod
    def ShuffleBlockS2(inputs, in_channels, out_channels, training=None, **kwargs):
        x = tf.keras.layers.Conv2D(filters=out_channels // 2,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same")(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.DepthwiseConv2D(kernel_size=(3, 3), strides=2, padding="same")(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.keras.layers.Conv2D(filters=out_channels - in_channels,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same")(x)
        x = tf.keras.layers.BatchNormalization()(x, training=training)
        x = tf.nn.swish(x)
        branch = tf.keras.layers.DepthwiseConv2D(kernel_size=(3, 3), strides=2, padding="same")(inputs)
        branch = tf.keras.layers.BatchNormalization()(branch, training=training)
        branch = tf.keras.layers.Conv2D(filters=in_channels,
                                        kernel_size=(1, 1),
                                        strides=1,
                                        padding="same")(branch)
        branch = tf.keras.layers.BatchNormalization()(branch, training=training)
        branch = tf.nn.swish(branch)
        outputs = tf.concat(values=[x, branch], axis=-1)
        outputs = ShuffleNetV2.channel_shuffle(feature=outputs, group=2)
        return outputs

    @staticmethod
    def _make_layer(inputs, repeat_num, in_channels, out_channels):
        x = ShuffleNetV2.ShuffleBlockS2(inputs, in_channels=in_channels, out_channels=out_channels)
        for _ in range(1, repeat_num):
            x = ShuffleNetV2.ShuffleBlockS1(x, in_channels=out_channels, out_channels=out_channels)
        return x

    @staticmethod
    def ShuffleNetV2(channel_scale, training=None, mask=None):
        inputs = tf.keras.layers.Input(shape=inputs_shape)
        x = tf.keras.layers.Conv2D(filters=24, kernel_size=(3, 3), strides=2, padding="same")(inputs)
        x = tf.keras.layers.BatchNormalization()(x, training)
        x = tf.nn.swish(x)
        x = tf.keras.layers.MaxPool2D(pool_size=(3, 3), strides=2, padding="same")(x)
        x = ShuffleNetV2._make_layer(x, repeat_num=4, in_channels=24, out_channels=channel_scale[0])
        x = ShuffleNetV2._make_layer(x, repeat_num=8, in_channels=channel_scale[0], out_channels=channel_scale[1])
        x = ShuffleNetV2._make_layer(x, repeat_num=4, in_channels=channel_scale[1], out_channels=channel_scale[2])
        x = tf.keras.layers.Conv2D(filters=channel_scale[3], kernel_size=(1, 1), strides=1, padding="same")(x)
        x = tf.keras.layers.BatchNormalization()(x, training)
        x = tf.keras.layers.GlobalAveragePooling2D()(x)
        outputs = tf.keras.layers.Dense(units=CAPTCHA_LENGTH * Settings.settings(),
                                        activation=tf.keras.activations.softmax)(x)
        outputs = tf.keras.layers.Reshape((CAPTCHA_LENGTH, Settings.settings()))(outputs)
        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        return model


# SqueezeNet
class SqueezeNet(object):
    @staticmethod
    def FireModule(inputs, s1, e1, e3, **kwargs):
        x = tf.keras.layers.Conv2D(filters=s1,
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same")(inputs)
        x = tf.nn.relu(x)
        y1 = tf.keras.layers.Conv2D(filters=e1,
                                    kernel_size=(1, 1),
                                    strides=1,
                                    padding="same")(x)
        y1 = tf.nn.relu(y1)
        y2 = tf.keras.layers.Conv2D(filters=e3,
                                    kernel_size=(3, 3),
                                    strides=1,
                                    padding="same")(x)
        y2 = tf.nn.relu(y2)
        return tf.concat(values=[y1, y2], axis=-1)

    @staticmethod
    def SqueezeNet(training=None, mask=None):
        inputs = tf.keras.layers.Input(shape=inputs_shape)
        x = tf.keras.layers.Conv2D(filters=96,
                                   kernel_size=(7, 7),
                                   strides=2,
                                   padding="same")(inputs)
        x = tf.keras.layers.MaxPool2D(pool_size=(3, 3),
                                      strides=2)(x)
        x = SqueezeNet.FireModule(x, s1=16, e1=64, e3=64)
        x = SqueezeNet.FireModule(x, s1=16, e1=64, e3=64)
        x = SqueezeNet.FireModule(x, s1=32, e1=128, e3=128)
        x = tf.keras.layers.MaxPool2D(pool_size=(3, 3),
                                      strides=2)(x)
        x = SqueezeNet.FireModule(x, s1=32, e1=128, e3=128)
        x = SqueezeNet.FireModule(x, s1=48, e1=192, e3=192)
        x = SqueezeNet.FireModule(x, s1=48, e1=192, e3=192)
        x = SqueezeNet.FireModule(x, s1=64, e1=256, e3=256)
        x = tf.keras.layers.MaxPool2D(pool_size=(3, 3),
                                      strides=2)(x)
        x = SqueezeNet.FireModule(x, s1=64, e1=256, e3=256)
        x = tf.keras.layers.Dropout(rate=0.5)(x)
        x = tf.keras.layers.Conv2D(filters=Settings.settings(),
                                   kernel_size=(1, 1),
                                   strides=1,
                                   padding="same")(x)
        outputs = tf.keras.layers.GlobalAveragePooling2D()(x)
        outputs = tf.keras.layers.Reshape((CAPTCHA_LENGTH, Settings.settings()))(outputs)
        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        return model


# MnasNet
class MnasNet(object):
    @staticmethod
    def conv_bn(x, filters, kernel_size, strides=1, alpha=1, activation=True):
        filters = MnasNet._make_divisible(filters * alpha)
        x = tf.keras.layers.Conv2D(filters=filters, kernel_size=kernel_size, strides=strides, padding='same',
                                   use_bias=False, kernel_regularizer=tf.keras.regularizers.l2(l=0.0003))(x)
        x = tf.keras.layers.BatchNormalization(epsilon=1e-3, momentum=0.999)(x)
        if activation:
            x = tf.keras.layers.ReLU(max_value=6)(x)
        return x

    @staticmethod
    def depthwiseConv_bn(x, depth_multiplier, kernel_size, strides=1):
        x = tf.keras.layers.DepthwiseConv2D(kernel_size=kernel_size, strides=strides, depth_multiplier=depth_multiplier,
                                            padding='same', use_bias=False,
                                            kernel_regularizer=tf.keras.regularizers.l2(l=0.0003))(x)
        x = tf.keras.layers.BatchNormalization(epsilon=1e-3, momentum=0.999)(x)
        x = tf.keras.layers.ReLU(max_value=6)(x)
        return x

    @staticmethod
    def sepConv_bn_noskip(x, filters, kernel_size, strides=1):
        x = MnasNet.depthwiseConv_bn(x, depth_multiplier=1, kernel_size=kernel_size, strides=strides)
        x = MnasNet.conv_bn(x, filters=filters, kernel_size=1, strides=1)

        return x

    @staticmethod
    def MBConv_idskip(x_input, filters, kernel_size, strides=1, filters_multiplier=1, alpha=1):
        depthwise_conv_filters = MnasNet._make_divisible(x_input.shape[3])
        pointwise_conv_filters = MnasNet._make_divisible(filters * alpha)

        x = MnasNet.conv_bn(x_input, filters=depthwise_conv_filters * filters_multiplier, kernel_size=1, strides=1)
        x = MnasNet.depthwiseConv_bn(x, depth_multiplier=1, kernel_size=kernel_size, strides=strides)
        x = MnasNet.conv_bn(x, filters=pointwise_conv_filters, kernel_size=1, strides=1, activation=False)
        if strides == 1 and x.shape[3] == x_input.shape[3]:
            return tf.keras.layers.add([x_input, x])
        else:
            return x

    @staticmethod
    def _make_divisible(v, divisor=8, min_value=None):
        if min_value is None:
            min_value = divisor
        new_v = max(min_value, int(v + divisor / 2) // divisor * divisor)
        if new_v < 0.9 * v:
            new_v += divisor
        return new_v

    @staticmethod
    def MnasNet():
        alpha = 1
        inputs = tf.keras.layers.Input(shape=inputs_shape)

        x = MnasNet.conv_bn(inputs, 32 * alpha, 3, strides=2)
        x = MnasNet.sepConv_bn_noskip(x, 16 * alpha, 3, strides=1)
        # MBConv3 3x3
        x = MnasNet.MBConv_idskip(x, filters=24, kernel_size=3, strides=2, filters_multiplier=3, alpha=alpha)
        x = MnasNet.MBConv_idskip(x, filters=24, kernel_size=3, strides=1, filters_multiplier=3, alpha=alpha)
        x = MnasNet.MBConv_idskip(x, filters=24, kernel_size=3, strides=1, filters_multiplier=3, alpha=alpha)
        # MBConv3 5x5
        x = MnasNet.MBConv_idskip(x, filters=40, kernel_size=5, strides=2, filters_multiplier=3, alpha=alpha)
        x = MnasNet.MBConv_idskip(x, filters=40, kernel_size=5, strides=1, filters_multiplier=3, alpha=alpha)
        x = MnasNet.MBConv_idskip(x, filters=40, kernel_size=5, strides=1, filters_multiplier=3, alpha=alpha)
        # MBConv6 5x5
        x = MnasNet.MBConv_idskip(x, filters=80, kernel_size=5, strides=2, filters_multiplier=6, alpha=alpha)
        x = MnasNet.MBConv_idskip(x, filters=80, kernel_size=5, strides=1, filters_multiplier=6, alpha=alpha)
        x = MnasNet.MBConv_idskip(x, filters=80, kernel_size=5, strides=1, filters_multiplier=6, alpha=alpha)
        # MBConv6 3x3
        x = MnasNet.MBConv_idskip(x, filters=96, kernel_size=3, strides=1, filters_multiplier=6, alpha=alpha)
        x = MnasNet.MBConv_idskip(x, filters=96, kernel_size=3, strides=1, filters_multiplier=6, alpha=alpha)
        # MBConv6 5x5
        x = MnasNet.MBConv_idskip(x, filters=192, kernel_size=5, strides=2, filters_multiplier=6, alpha=alpha)
        x = MnasNet.MBConv_idskip(x, filters=192, kernel_size=5, strides=1, filters_multiplier=6, alpha=alpha)
        x = MnasNet.MBConv_idskip(x, filters=192, kernel_size=5, strides=1, filters_multiplier=6, alpha=alpha)
        x = MnasNet.MBConv_idskip(x, filters=192, kernel_size=5, strides=1, filters_multiplier=6, alpha=alpha)
        # MBConv6 3x3
        x = MnasNet.MBConv_idskip(x, filters=320, kernel_size=3, strides=1, filters_multiplier=6, alpha=alpha)
        # FC + POOL
        x = MnasNet.conv_bn(x, filters=1152 * alpha, kernel_size=1, strides=1)
        x = tf.keras.layers.GlobalAveragePooling2D()(x)
        outputs = tf.keras.layers.Dense(CAPTCHA_LENGTH * Settings.settings(), activation='softmax')(x)
        outputs = tf.keras.layers.Reshape((CAPTCHA_LENGTH, Settings.settings()))(outputs)
        return tf.keras.models.Model(inputs=inputs, outputs=outputs)


class Settings(object):
    @staticmethod
    def settings():
        with open(n_class_file, 'r', encoding='utf-8') as f:
            n_class = len(json.loads(f.read()))
        return n_class + 1

    @staticmethod
    def settings_num_classes():
        with open(n_class_file, 'r', encoding='utf-8') as f:
            n_class = len(json.loads(f.read()))
        return n_class


class CTCLoss(tf.keras.losses.Loss):
    def __init__(self, logits_time_major=False, blank_index=-1,
                 reduction=tf.keras.losses.Reduction.AUTO, name='ctc_loss'):
        super().__init__(reduction=reduction, name=name)
        self.logits_time_major = logits_time_major
        self.blank_index = blank_index

    def call(self, y_true, y_pred):
        y_true = tf.cast(y_true, tf.int32)
        logit_length = tf.fill([tf.shape(y_pred)[0]], tf.shape(y_pred)[1])
        loss = tf.nn.ctc_loss(
            labels=y_true,
            logits=y_pred,
            label_length=None,
            logit_length=logit_length,
            logits_time_major=self.logits_time_major,
            blank_index=self.blank_index
        )
        return tf.reduce_mean(loss)


class WordAccuracy(tf.keras.metrics.Metric):

    def __init__(self, name='word_acc', **kwargs):
        super().__init__(name=name, **kwargs)
        self.total = self.add_weight(name='total', dtype=tf.int32,
                                     initializer=tf.zeros_initializer())
        self.count = self.add_weight(name='count', dtype=tf.int32,
                                     initializer=tf.zeros_initializer())

    def update_state(self, y_true, y_pred, sample_weight=None):
        b = tf.shape(y_true)[0]
        max_width = tf.maximum(tf.shape(y_true)[1], tf.shape(y_pred)[1])
        logit_length = tf.fill([tf.shape(y_pred)[0]], tf.shape(y_pred)[1])
        decoded, _ = tf.nn.ctc_greedy_decoder(
            inputs=tf.transpose(y_pred, perm=[1, 0, 2]),
            sequence_length=logit_length)
        y_true = tf.sparse.reset_shape(y_true, [b, max_width])
        y_pred = tf.sparse.reset_shape(decoded[0], [b, max_width])
        y_true = tf.sparse.to_dense(y_true, default_value=-1)
        y_pred = tf.sparse.to_dense(y_pred, default_value=-1)
        y_true = tf.cast(y_true, tf.int32)
        y_pred = tf.cast(y_pred, tf.int32)
        values = tf.math.reduce_any(tf.math.not_equal(y_true, y_pred), axis=1)
        values = tf.cast(values, tf.int32)
        values = tf.reduce_sum(values)
        self.total.assign_add(b)
        self.count.assign_add(b - values)

    def result(self):
        return self.count / self.total

    def reset_states(self):
        self.count.assign(0)
        self.total.assign(0)


class Models(object):
    @staticmethod
    def captcha_model():
        model = Densenet.Densenet(num_init_features=64, growth_rate=32, block_layers=[6, 12, 32, 32],
                                  compression_rate=0.5,
                                  drop_rate=0.5)
        model.compile(optimizer=tf.keras.optimizers.Nadam(learning_rate=LR, beta_1=0.5, beta_2=0.9),
                      loss=tf.keras.losses.CategoricalCrossentropy(label_smoothing=0.1),
                      metrics=['acc'])
        return model

    @staticmethod
    def captcha_model_num_classes():
        model = Densenet.Densenet_num_classes(num_init_features=64, growth_rate=32, block_layers=[6, 12, 64, 48],
                                              compression_rate=0.5,
                                              drop_rate=0.5)
        model.compile(optimizer=tf.keras.optimizers.Nadam(learning_rate=LR),
                      loss=tf.keras.losses.CategoricalCrossentropy(label_smoothing=0.1),
                      metrics=['acc'])
        return model

    @staticmethod
    def captcha_model_ctc():
        inputs = tf.keras.layers.Input(shape=inputs_shape)
        x = tf.keras.layers.Conv2D(filters=64, kernel_size=3, padding='same',
                                   kernel_initializer=tf.keras.initializers.he_normal())(
            inputs)
        x = tf.nn.swish(x)
        x = tf.keras.layers.BatchNormalization(epsilon=1e-05, axis=1, momentum=0.1)(x)
        x = tf.keras.layers.Conv2D(filters=64, kernel_size=3, padding='same')(x)
        x = tf.nn.swish(x)
        x = tf.keras.layers.BatchNormalization(epsilon=1e-05, axis=1, momentum=0.1)(x)
        x = tf.keras.layers.MaxPool2D(pool_size=(2, 2), padding='same')(x)
        x = tf.keras.layers.Conv2D(filters=128, kernel_size=3, padding='same')(x)
        x = tf.nn.swish(x)
        x = tf.keras.layers.BatchNormalization(epsilon=1e-05, axis=1, momentum=0.1)(x)
        x = tf.keras.layers.MaxPool2D(pool_size=(2, 2), padding='same')(x)
        x = tf.keras.layers.Conv2D(filters=256, kernel_size=3, padding='same')(x)
        x = tf.nn.swish(x)
        x = tf.keras.layers.BatchNormalization(epsilon=1e-05, axis=1, momentum=0.1)(x)
        x = tf.keras.layers.MaxPool2D(pool_size=(2, 2), strides=(2, 1), padding='same')(x)
        x = tf.keras.layers.Conv2D(filters=512, kernel_size=3, padding='same')(x)
        x = tf.nn.swish(x)
        x = tf.keras.layers.BatchNormalization(epsilon=1e-05, axis=1, momentum=0.1)(x)
        x = tf.keras.layers.Conv2D(filters=512, kernel_size=3, padding='same')(x)
        x = tf.nn.swish(x)
        x = tf.keras.layers.BatchNormalization(epsilon=1e-05, axis=1, momentum=0.1)(x)
        x = tf.keras.layers.MaxPool2D(pool_size=(2, 2), strides=(2, 1), padding='same')(x)
        x = tf.keras.layers.Conv2D(filters=512, kernel_size=2, padding='same',
                                   kernel_initializer=tf.keras.initializers.he_normal())(x)
        x = tf.nn.swish(x)
        x = tf.keras.layers.BatchNormalization(epsilon=1e-05, axis=1, momentum=0.1)(x)
        x = tf.keras.layers.Conv2D(filters=512, kernel_size=2, padding='same',
                                   kernel_initializer=tf.keras.initializers.he_normal())(x)
        x = tf.nn.swish(x)
        x = tf.keras.layers.BatchNormalization(epsilon=1e-05, axis=1, momentum=0.1)(x)
        x = tf.keras.layers.Reshape((-1, 512))(x)
        x = tf.keras.layers.Bidirectional(
            tf.keras.layers.LSTM(units=256, return_sequences=True, use_bias=True, recurrent_activation='sigmoid'))(
            x)
        x = tf.keras.layers.Bidirectional(
            tf.keras.layers.LSTM(units=256, return_sequences=True, use_bias=True, recurrent_activation='sigmoid'))(
            x)
        outputs = tf.keras.layers.Dense(units=Settings.settings())(x)
        model = tf.keras.Model(inputs=inputs, outputs=outputs)
        model.compile(optimizer=tf.keras.optimizers.Nadam(learning_rate=LR, beta_1=0.5, beta_2=0.9),
                      loss=CTCLoss(), metrics=[WordAccuracy()])
        return model


# Densenet_121 = Densenet.Densenet(num_init_features=64, growth_rate=32, block_layers=[6, 12, 24, 16],
#                                  compression_rate=0.5,
#                                  drop_rate=0.5)
# Densenet_169 = Densenet.Densenet(num_init_features=64, growth_rate=32, block_layers=[6, 12, 32, 32],
#                                  compression_rate=0.5,
#                                  drop_rate=0.5)
# Densenet_201 = Densenet.Densenet(num_init_features=64, growth_rate=32, block_layers=[6, 12, 48, 32],
#                                  compression_rate=0.5,
#                                  drop_rate=0.5)
# Densenet_264 = Densenet.Densenet(num_init_features=64, growth_rate=32, block_layers=[6, 12, 64, 48],
#                                  compression_rate=0.5,
#                                  drop_rate=0.5)
# Efficient_net_b0 = Efficientnet.Efficientnet(width_coefficient=1.0, depth_coefficient=1.0, dropout_rate=0.2)
# Efficient_net_b1 = Efficientnet.Efficientnet(width_coefficient=1.0, depth_coefficient=1.1, dropout_rate=0.2)
# Efficient_net_b2 = Efficientnet.Efficientnet(width_coefficient=1.1, depth_coefficient=1.2, dropout_rate=0.3)
# Efficient_net_b3 = Efficientnet.Efficientnet(width_coefficient=1.2, depth_coefficient=1.4, dropout_rate=0.3)
# Efficient_net_b4 = Efficientnet.Efficientnet(width_coefficient=1.4, depth_coefficient=1.8, dropout_rate=0.4)
# Efficient_net_b5 = Efficientnet.Efficientnet(width_coefficient=1.6, depth_coefficient=2.2, dropout_rate=0.4)
# Efficient_net_b6 = Efficientnet.Efficientnet(width_coefficient=1.8, depth_coefficient=2.6, dropout_rate=0.5)
# Efficient_net_b7 = Efficientnet.Efficientnet(width_coefficient=2.0, depth_coefficient=3.1, dropout_rate=0.5)
# MobileNetV1 = Mobilenet.MobileNetV1()
# MobileNetV2 = Mobilenet.MobileNetV2()
# MobileNetV3Large = Mobilenet.MobileNetV3Large()
# MobileNetV3Small = Mobilenet.MobileNetV3Small()
# Resnet_18 = ResNeXt.ResNetTypeI(layer_params=(2, 2, 2, 2))
# Resnet_34 = ResNeXt.ResNetTypeI(layer_params=(3, 4, 6, 3))
# Resnet_50 = ResNeXt.ResNetTypeII(layer_params=(3, 4, 6, 3))
# Resnet_101 = ResNeXt.ResNetTypeII(layer_params=(3, 4, 23, 3))
# Resnet_152 = ResNeXt.ResNetTypeII(layer_params=(3, 8, 36, 3))
# ResNeXt50 = ResNeXt.Resnext(repeat_num_list=(3, 4, 6, 3), cardinality=32)
# ResNeXt101 = ResNeXt.Resnext(repeat_num_list=(3, 4, 23, 3), cardinality=32)
# SEResNet50 = SEResNet.SEResNet(block_num=[3, 4, 6, 3])
# SEResNet152 = SEResNet.SEResNet(block_num=[3, 8, 36, 3])
# ShuffleNet_0_5x = ShuffleNetV2.ShuffleNetV2(channel_scale=[48, 96, 192, 1024])
# ShuffleNet_1_0x = ShuffleNetV2.ShuffleNetV2(channel_scale=[116, 232, 464, 1024])
# ShuffleNet_1_5x = ShuffleNetV2.ShuffleNetV2(channel_scale=[176, 352, 704, 1024])
# ShuffleNet_2_0x = ShuffleNetV2.ShuffleNetV2(channel_scale=[244, 488, 976, 2048])
# SqueezeNet = SqueezeNet.SqueezeNet()


if __name__ == '__main__':
    with tf.device('/cpu:0'):
        model = Models.captcha_model()
        model.summary()
        # model._layers = [layer for layer in model.layers if not isinstance(layer, dict)]
        # tf.keras.utils.plot_model(model, show_shapes=True, dpi=48)

"""


def move_path(work_path, project_name):
    return f"""import random
from {work_path}.{project_name}.settings import train_path
from {work_path}.{project_name}.utils import Image_Processing

train_image = Image_Processing.extraction_image(train_path)
random.shuffle(train_image)
Image_Processing.move_path(train_image)

"""


def pack_dataset(work_path, project_name):
    return f"""import random
from loguru import logger
from {work_path}.{project_name}.settings import train_path
from {work_path}.{project_name}.settings import validation_path
from {work_path}.{project_name}.settings import test_path
from {work_path}.{project_name}.settings import train_enhance_path
from {work_path}.{project_name}.settings import DATA_ENHANCEMENT
from {work_path}.{project_name}.settings import TFRecord_train_path
from {work_path}.{project_name}.settings import TFRecord_validation_path
from {work_path}.{project_name}.settings import TFRecord_test_path
from {work_path}.{project_name}.utils import Image_Processing
from {work_path}.{project_name}.utils import WriteTFRecord
from concurrent.futures import ThreadPoolExecutor

if DATA_ENHANCEMENT:
    image_path = Image_Processing.extraction_image(train_path)
    number = len(image_path)
    with ThreadPoolExecutor(max_workers=100) as t:
        for i in image_path:
            number = number - 1
            task = t.submit(Image_Processing.preprosess_save_images, i, number)
    train_image = Image_Processing.extraction_image(train_enhance_path)
    random.shuffle(train_image)

else:
    train_image = Image_Processing.extraction_image(train_path)
    random.shuffle(train_image)
validation_image = Image_Processing.extraction_image(validation_path)
test_image = Image_Processing.extraction_image(test_path)

Image_Processing.extraction_label(train_image + validation_image + test_image)

train_lable = Image_Processing.extraction_label(train_image)
validation_lable = Image_Processing.extraction_label(validation_image)
test_lable = Image_Processing.extraction_label(test_image)
# logger.debug(train_image)
# logger.debug(train_lable)
#
with ThreadPoolExecutor(max_workers=3) as t:
    t.submit(WriteTFRecord.WriteTFRecord, TFRecord_train_path, train_image, train_lable, 'train', 10000)
    t.submit(WriteTFRecord.WriteTFRecord, TFRecord_validation_path, validation_image, validation_lable, 'validation',
             10000)
    t.submit(WriteTFRecord.WriteTFRecord, TFRecord_test_path, test_image, test_lable, 'test', 10000)

"""


def rename_suffix(work_path, project_name):
    return f"""from {work_path}.{project_name}.settings import train_path
from {work_path}.{project_name}.utils import Image_Processing


Image_Processing.rename_suffix(Image_Processing.extraction_image(train_path))

"""


def save_model(work_path, project_name):
    return f"""import os
import operator
from loguru import logger
from {work_path}.{project_name}.models import Models
from {work_path}.{project_name}.callback import CallBack
from {work_path}.{project_name}.settings import MODEL
from {work_path}.{project_name}.settings import MODEL_NAME
from {work_path}.{project_name}.settings import model_path
from {work_path}.{project_name}.settings import checkpoint_path

model = operator.methodcaller(MODEL)(Models)
try:
    weight = CallBack.calculate_the_best_weight()
    logger.info(f'读取的权重为{{weight}}')
    model.load_weights(os.path.join(checkpoint_path, weight))
except:
    raise OSError(f'没有任何的权重和模型在{{model_path}}')
model_path = os.path.join(model_path, MODEL_NAME)
model.save(model_path)
logger.debug(f'{{model_path}}模型保存成功')
"""


def settings(work_path, project_name):
    return f"""import os
import datetime

## 硬件配置
# 是否使用GPU
USE_GPU = True

# CPU的核心数，请根据自己的CPU来进行设置，正确选择核心数对训练有利
CPU_NUMBER = 4

# 模式选择 ORDINARY默认模式，需要设置验证码的长度 | NUM_CLASSES图片分类 | CTC识别文字，不需要文本设置长度
MODE = 'ORDINARY'

## 超参数设置
# 学习率
LR = 1e-4

#是否使用余弦退火衰减(默认关闭,False使用的是常数衰减)
COSINE_SCHEDULER = False

# 训练次数
EPOCHS = 200

# batsh批次
BATCH_SIZE = 16

# 训练多少轮验证损失下不去，学习率/10
LR_PATIENCE = 2

# 训练多少轮验证损失下不去，停止训练
EARLY_PATIENCE = 16

## 图片设置请先运行check_file.py查看图片的宽和高，设置的高和宽最好大于你的数据集的高和宽
# 图片高度
IMAGE_HEIGHT = 80

# 图片宽度
IMAGE_WIDTH = 240

# 图片通道
IMAGE_CHANNALS = 3

# 验证码的长度
CAPTCHA_LENGTH = 8

# 是否使用数据增强(数据集多的时候不需要用，接收一个整数，代表增强多少张图片)
DATA_ENHANCEMENT = False

## 模型设置
# 定义模型的方法,模型在models.py定义
MODEL = 'captcha_model'

# 保存的模型名称
MODEL_NAME = 'captcha.h5'

## 路径设置，一般无需改动
# 可视化配置batch或epoch
UPDATE_FREQ = 'epoch'

# 训练集路径
train_path = os.path.join(os.getcwd(), 'train_dataset')

# 增强后的路径
train_enhance_path = os.path.join(os.getcwd(), 'train_enhance_dataset')

# 验证集路径
validation_path = os.path.join(os.getcwd(), 'validation_dataset')

# 测试集路径
test_path = os.path.join(os.getcwd(), 'test_dataset')

# 标签路径
label_path = os.path.join(os.getcwd(), 'label')

# 打包训练集路径
TFRecord_train_path = os.path.join(os.getcwd(), 'train_pack_dataset')

# 打包验证集
TFRecord_validation_path = os.path.join(os.getcwd(), 'validation_pack_dataset')

# 打包测试集路径
TFRecord_test_path = os.path.join(os.getcwd(), 'test_pack_dataset')

# 模型保存路径
model_path = os.path.join(os.getcwd(), 'model')

# 可视化日志路径
log_dir = os.path.join(os.path.join(os.getcwd(), 'logs'), f'{{datetime.datetime.now().strftime("%Y%m%d-%H%M%S")}}')

# csv_logger日志路径
csv_path = os.path.join(os.path.join(os.getcwd(), 'CSVLogger'), 'traing.csv')

# 断点续训路径
checkpoint_path = os.path.join(os.getcwd(), 'checkpoint')  # 检查点路径

# checkpoint_file_path = os.path.join(checkpoint_path,
#                                     'Model_weights.-{{epoch:02d}}-{{val_loss:.4f}}.hdf5')
if MODE == 'CTC':
    checkpoint_file_path = os.path.join(checkpoint_path,
                                        'Model_weights.-{{epoch:02d}}-{{val_loss:.4f}}-{{val_word_acc:.4f}}.hdf5')
else:
    checkpoint_file_path = os.path.join(checkpoint_path,
                                        'Model_weights.-{{epoch:02d}}-{{val_loss:.4f}}-{{val_acc:.4f}}.hdf5')
# TF训练集(打包后)
train_pack_path = os.path.join(os.getcwd(), 'train_pack_dataset')

# TF验证集(打包后)
validation_pack_path = os.path.join(os.getcwd(), 'validation_pack_dataset')

# TF测试集(打包后)
test_pack_path = os.path.join(os.getcwd(), 'test_pack_dataset')

# 提供后端放置的模型路径
App_model_path = os.path.join(os.getcwd(), 'App_model')

# 映射表
n_class_file = os.path.join(os.getcwd(), 'num_classes.json')
"""


def spider_example(work_path, project_name):
    return f"""import time
import base64
import random
import requests
from loguru import logger


def get_captcha():
    r = int(random.random() * 100000000)
    params = {{
        'r': str(r),
        's': '0',
    }}
    response = requests.get('https://login.sina.com.cn/cgi/pin.php', params=params)
    if response.status_code == 200:
        return response.content


if __name__ == '__main__':
    content = get_captcha()
    if content:
        logger.info(f'获取验证码成功')
        with open(f'{{int(time.time())}}.jpg', 'wb') as f:
            f.write(content)
        data = {{'img': base64.b64encode(content)}}
        response = requests.post('http://127.0.0.1:5006', data=data)
        logger.debug(response.json())
        if response.json().get('return_info') == '处理成功':
            logger.debug(f'验证码为{{response.json().get("result")}}')
        else:
            logger.error('识别失败')

    else:
        logger.error(f'获取验证码失败')

"""


def sub_filename(work_path, project_name):
    return f"""from {work_path}.{project_name}.settings import train_path
from {work_path}.{project_name}.utils import Image_Processing

train_image = Image_Processing.extraction_image(train_path)
Image_Processing.rename_path(train_image)
"""


def test(work_path, project_name):
    return f"""import os
import time
import random
import tensorflow as tf
from loguru import logger
from {work_path}.{project_name}.settings import MODE
from {work_path}.{project_name}.settings import USE_GPU
from {work_path}.{project_name}.settings import test_path
from {work_path}.{project_name}.settings import model_path
from {work_path}.{project_name}.settings import n_class_file
from {work_path}.{project_name}.settings import MODEL_NAME
from {work_path}.{project_name}.models import CTCLoss
from {work_path}.{project_name}.models import WordAccuracy
from {work_path}.{project_name}.models import DropBlock
from {work_path}.{project_name}.utils import Image_Processing
from {work_path}.{project_name}.utils import Predict_Image


def running_time(time):
    m = time / 60
    h = m / 60
    if m > 1:
        if h > 1:
            return str(h) + 'h'
        else:
            return str(m) + 'm'
    else:
        return str(time) + 's'


start = time.time()
if USE_GPU:
    gpus = tf.config.experimental.list_physical_devices(device_type="GPU")
    if gpus:
        logger.info("use gpu device")
        logger.info(f'可用GPU数量: {{len(gpus)}}')
        try:
            tf.config.experimental.set_visible_devices(gpus[0], 'GPU')
        except RuntimeError as e:
            logger.error(e)
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(device=gpu, enable=True)
            tf.print(gpu)
    else:
        tf.config.experimental.list_physical_devices(device_type="CPU")
        os.environ["CUDA_VISIBLE_DEVICE"] = "-1"
        logger.info("not found gpu device,convert to use cpu")
else:
    logger.info("use cpu device")
    # 禁用gpu
    tf.config.experimental.list_physical_devices(device_type="CPU")
    os.environ["CUDA_VISIBLE_DEVICE"] = "-1"

test_image_list = Image_Processing.extraction_image(test_path)
random.shuffle(test_image_list)

model_path = os.path.join(model_path, MODEL_NAME)
logger.debug(f'加载模型{{model_path}}')
if not os.path.exists(model_path):
    raise OSError(f'{{model_path}}没有模型')

if MODE == 'CTC':
    model = tf.keras.models.load_model(model_path, custom_objects={{'CTCLoss': CTCLoss, 'WordAccuracy': WordAccuracy}})
else:
    model = tf.keras.models.load_model(model_path, custom_objects={{'DropBlock': DropBlock}})

for i in test_image_list:
    Predict_Image(model=model, image=i, num_classes=n_class_file).predict_image()

end = time.time()
logger.info(f'总共运行时间{{running_time(end - start)}}')

"""


def train(work_path, project_name):
    return f"""import os
import operator
import pandas as pd
import tensorflow as tf
from loguru import logger
from {work_path}.{project_name}.models import Models
from {work_path}.{project_name}.callback import CallBack
from {work_path}.{project_name}.settings import MODEL
from {work_path}.{project_name}.settings import EPOCHS
from {work_path}.{project_name}.settings import USE_GPU
from {work_path}.{project_name}.settings import CPU_NUMBER
from {work_path}.{project_name}.settings import BATCH_SIZE
from {work_path}.{project_name}.settings import model_path
from {work_path}.{project_name}.settings import MODEL_NAME
from {work_path}.{project_name}.settings import DATA_ENHANCEMENT
from {work_path}.{project_name}.settings import csv_path
from {work_path}.{project_name}.settings import train_path
from {work_path}.{project_name}.settings import train_pack_path
from {work_path}.{project_name}.settings import train_enhance_path
from {work_path}.{project_name}.settings import validation_pack_path
from {work_path}.{project_name}.utils import cheak_path
from {work_path}.{project_name}.utils import parse_function
from {work_path}.{project_name}.utils import Image_Processing

if USE_GPU:
    gpus = tf.config.experimental.list_physical_devices(device_type="GPU")
    if gpus:
        logger.success(f'GPU_DEVICE_NAME:{{tf.test.gpu_device_name()}}')
        logger.success("use gpu device")
        logger.success(f'可用GPU数量: {{len(gpus)}}')
        try:
            tf.config.experimental.set_visible_devices(gpus[0], 'GPU')
        except RuntimeError as e:
            logger.error(e)
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(device=gpu, enable=True)
            tf.print(gpu)
    else:
        tf.config.experimental.list_physical_devices(device_type="CPU")
        os.environ["CUDA_VISIBLE_DEVICE"] = "-1"
        logger.error("not found gpu device,convert to use cpu")
else:
    logger.info("use cpu device")
    # 禁用gpu
    tf.config.experimental.list_physical_devices(device_type="CPU")
    os.environ["CUDA_VISIBLE_DEVICE"] = "-1"

with tf.device('/cpu:0'):
    train_dataset = tf.data.TFRecordDataset(Image_Processing.extraction_image(train_pack_path)).map(
        map_func=parse_function, num_parallel_calls=CPU_NUMBER).batch(batch_size=BATCH_SIZE).prefetch(
        buffer_size=BATCH_SIZE)
    logger.debug(train_dataset)
    validation_dataset = tf.data.TFRecordDataset(Image_Processing.extraction_image(validation_pack_path)).map(
        map_func=parse_function, num_parallel_calls=CPU_NUMBER).batch(batch_size=BATCH_SIZE).prefetch(
        buffer_size=BATCH_SIZE)

model, c_callback = CallBack.callback(operator.methodcaller(MODEL)(Models))

model.summary()

if DATA_ENHANCEMENT:
    logger.info(f'一共有{{int(len(Image_Processing.extraction_image(train_enhance_path)) / BATCH_SIZE)}}个batch')
else:
    logger.info(f'一共有{{int(len(Image_Processing.extraction_image(train_path)) / BATCH_SIZE)}}个batch')

try:
    logs = pd.read_csv(csv_path)
    data = logs.iloc[-1]
    initial_epoch = int(data.get('epoch')) + 1
except:
    initial_epoch = 0

model.fit(train_dataset, initial_epoch=initial_epoch, epochs=EPOCHS, callbacks=c_callback,
          validation_data=validation_dataset,
          verbose=2)

save_model_path = cheak_path(os.path.join(model_path, MODEL_NAME))

model.save(save_model_path, save_format='tf')
"""


class New_Work(object):
    def __init__(self, work_path='works', project_name='project'):
        self.work_parh = work_path
        self.project_name = project_name
        self.work = os.path.join(os.getcwd(), work_path)
        if not os.path.exists(self.work):
            os.mkdir(self.work)
        self.path = os.path.join(self.work, self.project_name)
        if not os.path.exists(self.path):
            os.mkdir(self.path)
        else:
            raise OSError('已有的项目')

    def file_name(self, name):
        return os.path.join(self.path, name)

    def callback(self):
        with open(self.file_name('callback.py'), 'w', encoding='utf-8') as f:
            f.write(callback(self.work_parh, self.project_name))

    def app(self):
        with open(self.file_name('app.py'), 'w', encoding='utf-8') as f:
            f.write(app(self.work_parh, self.project_name))

    def captcha_config(self):
        with open(self.file_name('captcha_config.json'), 'w') as f:
            f.write(captcha_config())

    def check_file(self):
        with open(self.file_name('check_file.py'), 'w', encoding='utf-8') as f:
            f.write(check_file(self.work_parh, self.project_name))

    def delete_file(self):
        with open(self.file_name('delete_file.py'), 'w', encoding='utf-8') as f:
            f.write(delete_file(self.work_parh, self.project_name))

    def utils(self):
        with open(self.file_name('utils.py'), 'w', encoding='utf-8') as f:
            f.write(utils(self.work_parh, self.project_name))

    def gen_sample_by_captcha(self):
        with open(self.file_name('gen_sample_by_captcha.py'), 'w', encoding='utf-8') as f:
            f.write(gen_sample_by_captcha(self.work_parh, self.project_name))

    def init_working_space(self):
        with open(self.file_name('init_working_space.py'), 'w', encoding='utf-8') as f:
            f.write(init_working_space(self.work_parh, self.project_name))

    def models(self):
        with open(self.file_name('models.py'), 'w', encoding='utf-8') as f:
            f.write(models(self.work_parh, self.project_name))

    def move_path(self):
        with open(self.file_name('move_path.py'), 'w', encoding='utf-8') as f:
            f.write(move_path(self.work_parh, self.project_name))

    def pack_dataset(self):
        with open(self.file_name('pack_dataset.py'), 'w', encoding='utf-8') as f:
            f.write(pack_dataset(self.work_parh, self.project_name))

    def rename_suffix(self):
        with open(self.file_name('rename_suffix.py'), 'w', encoding='utf-8') as f:
            f.write(rename_suffix(self.work_parh, self.project_name))

    def save_model(self):
        with open(self.file_name('save_model.py'), 'w', encoding='utf-8') as f:
            f.write(save_model(self.work_parh, self.project_name))

    def settings(self):
        with open(self.file_name('settings.py'), 'w', encoding='utf-8') as f:
            f.write(settings(self.work_parh, self.project_name))

    def spider_example(self):
        with open(self.file_name('spider_example.py'), 'w', encoding='utf-8') as f:
            f.write(spider_example(self.work_parh, self.project_name))

    def sub_filename(self):
        with open(self.file_name('sub_filename.py'), 'w', encoding='utf-8') as f:
            f.write(sub_filename(self.work_parh, self.project_name))

    def test(self):
        with open(self.file_name('test.py'), 'w', encoding='utf-8') as f:
            f.write(test(self.work_parh, self.project_name))

    def train(self):
        with open(self.file_name('train.py'), 'w', encoding='utf-8') as f:
            f.write(train(self.work_parh, self.project_name))

    def main(self):
        self.callback()
        self.app()
        self.captcha_config()
        self.check_file()
        self.delete_file()
        self.utils()
        self.gen_sample_by_captcha()
        self.init_working_space()
        self.models()
        self.move_path()
        self.pack_dataset()
        self.rename_suffix()
        self.save_model()
        self.settings()
        self.spider_example()
        self.sub_filename()
        self.test()
        self.train()


if __name__ == '__main__':
    New_Work(work_path='works', project_name='simple').main()
