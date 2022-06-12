# Copied from https://www.tensorflow.org/tfx/tutorials/tfx/penguin_simple

from typing import List
from absl import logging
import tensorflow as tf
from tensorflow import keras
from tensorflow_transform.tf_metadata import schema_utils

from tfx import v1 as tfx
from tfx_bsl.public import tfxio

from tensorflow_metadata.proto.v0 import schema_pb2


_FEATURE_KEYS = [
    'pickup_latitude', 'pickup_longitude', 'dropoff_latitude', 'dropoff_longitude', 'euclidean'
]
_LABEL_KEY = 'trip_total'


_TRAIN_BATCH_SIZE = 128 #dataset_size / batch size = # of steps
_EVAL_BATCH_SIZE = 64


_FEATURE_SPEC = {
    **{
        feature: tf.io.FixedLenFeature(shape=[1], dtype=tf.float32)
           for feature in _FEATURE_KEYS
       },
    _LABEL_KEY: tf.io.FixedLenFeature(shape=[1], dtype=tf.float32)
}


def _input_fn(file_pattern: List[str],
              data_accessor: tfx.components.DataAccessor,
              schema: schema_pb2.Schema,
              batch_size: int) -> tf.data.Dataset:
  """Generates features and label for training.

  Args:
    file_pattern: List of paths or patterns of input tfrecord files.
    data_accessor: DataAccessor for converting input to RecordBatch.
    schema: schema of the input data.
    batch_size: representing the number of consecutive elements of returned
      dataset to combine in a single batch

  Returns:
    A dataset that contains (features, indices) tuple where features is a
      dictionary of Tensors, and indices is a single Tensor of label indices.
  """
  return data_accessor.tf_dataset_factory(
      file_pattern,
      tfxio.TensorFlowDatasetOptions(
          batch_size=batch_size, label_key=_LABEL_KEY),
      schema=schema).repeat()


def _make_keras_model() -> tf.keras.Model:
  """Creates a DNN Keras model for classifying penguin data.

  Returns:
    A Keras Model.
  """
  # The model below is built with Functional API, please refer to
  # https://www.tensorflow.org/guide/keras/overview for all API options.
  inputs = [keras.layers.Input(shape=(1,), name=f) for f in _FEATURE_KEYS]
  d = keras.layers.concatenate(inputs)
  for _ in range(2):
    # d = keras.layers.Dense(8, activation='relu')(d)
    d = keras.layers.Dense(64, activation='relu')(d)
    d = keras.layers.Dense(32, activation='relu')(d)
    d = keras.layers.Dense(16, activation='relu')(d)
  # outputs = keras.layers.Dense(3)(d)
    outputs = keras.layers.Dense(1, activation='linear')(d)

  model = keras.Model(inputs=inputs, outputs=outputs)

  # model.compile(
  #     optimizer=keras.optimizers.Adam(1e-2),
  #     loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True),
  #     metrics=[keras.metrics.SparseCategoricalAccuracy()])
    
  model.compile(
      optimizer=keras.optimizers.Adam(0.00001),
      loss=tf.keras.losses.MeanSquaredError(),
      metrics=[keras.metrics.MeanSquaredError(), keras.metrics.MeanAbsoluteError()])

  model.summary(print_fn=logging.info)
  return model

# NEW: Read `use_gpu` from the custom_config of the Trainer.
#      if it uses GPU, enable MirroredStrategy.
def _get_distribution_strategy(fn_args: tfx.components.FnArgs):
  if fn_args.custom_config.get('use_gpu', False):
    logging.info('Using MirroredStrategy with one GPU.')
    return tf.distribute.MirroredStrategy(devices=['device:GPU:0'])
  return None

# TFX Trainer  tfx.components.Trainer will call this function.
def run_fn(fn_args: tfx.components.FnArgs):
  """Train the model based on given args.

  Args:
    fn_args: Holds args used to train the model as name/value pairs.
  """

  # This schema is usually either an output of SchemaGen or a manually-curated
  # version provided by pipeline author. A schema can also derived from TFT
  # graph if a Transform component is used. In the case when either is missing,
  # `schema_from_feature_spec` could be used to generate schema from very simple
  # feature_spec, but the schema returned would be very primitive.
  print('YAHOOOOOOOOOOOOOO')
  #Load the schema from Feature Specs
  schema = schema_utils.schema_from_feature_spec(_FEATURE_SPEC)
    
  train_dataset = _input_fn(
      fn_args.train_files,
      fn_args.data_accessor,
      schema,
      batch_size=_TRAIN_BATCH_SIZE)

  eval_dataset = _input_fn(
      fn_args.eval_files,
      fn_args.data_accessor,
      schema,
      batch_size=_EVAL_BATCH_SIZE)
    
  # NEW: If we have a distribution strategy, build a model in a strategy scope.
  strategy = _get_distribution_strategy(fn_args)
  if strategy is None:
    model = _make_keras_model()
  else:
    with strategy.scope():
      model = _make_keras_model()

  tensorboard_callback = tf.keras.callbacks.TensorBoard(log_dir=fn_args.model_run_dir, update_freq='batch')
    
  model.fit(
      train_dataset,
      epochs = 10,
      steps_per_epoch=fn_args.train_steps,
      validation_data=eval_dataset,
      validation_steps=fn_args.eval_steps,
      callbacks=[tensorboard_callback])

  # The result of the training should be saved in `fn_args.serving_model_dir`
  # directory.
  model.save(fn_args.serving_model_dir, save_format='tf')