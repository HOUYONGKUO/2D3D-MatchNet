#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Sun May 27 12:57:47 2018

@author: mengdan
"""

#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Fri May 18 20:25:02 2018

@author: mengdan
"""

import tensorflow as tf
import numpy as np

from vgg16 import vgg16
from pointNet import pointNet
from read_dataset import Data, splitTrainTest, shuffleTrainset
from metricNet import metricNet


batch_size = 64
image_size = 128
pcl_size = 1024
image_feature_dim = 128
pcl_feature_dim = 128

learning_rate_val = 6e-5

epoch_time = 10



def restore_tf_model(sess):
    save_path = 'model/init/vgg_init_model.ckpt'
    print('restore_tf_model(sess, %s)' % save_path)

    var_not_restore = ['metric_net/fc1/weights/Adam:0',
                        'metric_net/fc1/weights/Adam_1:0',
                        'metric_net/fc1/biases/Adam:0',
                        'metric_net/fc1/biases/Adam_1:0',
                        'metric_net/fc2/weights/Adam:0',
                        'metric_net/fc2/weights/Adam_1:0',
                        'metric_net/fc2/biases/Adam:0',
                        'metric_net/fc2/biases/Adam_1:0',
                        'metric_net/fc3/weights/Adam:0',
                        'metric_net/fc3/weights/Adam_1:0',
                        'metric_net/fc3/biases/Adam:0',
                        'metric_net/fc3/biases/Adam_1:0',
                        'metric_net/fc1/weights:0',
                        'metric_net/fc1/biases:0',
                        'metric_net/fc2/weights:0',
                        'metric_net/fc2/biases:0',
                        'metric_net/fc3/weights:0',
                        'metric_net/fc3/biases:0']

    for v in tf.global_variables():
        print('\'%s\',' % v.name)
    exit(0)

    restore_var = [v for v in tf.global_variables() if v.name not in var_not_restore]

    saver = tf.train.Saver(var_list=restore_var)  # tf.global_variables
    saver.restore(sess, save_path)
    print("Model loaded from: %s" % save_path)

def cross_entropy_loss(img_pos_feature, img_neg_feature, pos_label, neg_label):
    '''
    objective: compute cross-entropy loss
    img_pos_feature: Bx2
    img_neg_feature: Bx2
    '''
    pos_loss = tf.nn.softmax_cross_entropy_with_logits(labels=pos_label, logits=img_pos_feature)
    neg_loss = tf.nn.softmax_cross_entropy_with_logits(labels=neg_label, logits=img_neg_feature)
    
    loss = pos_loss + neg_loss
    
    return loss

def ComputeAccuracy(img_feature, pcl_feature):
    '''
    Compute top1 accuracy
    '''
    # find unique pcl_feature
    unique_pcl_feature, index = np.unique(pcl_feature, axis=0, return_inverse=True)
    print ('Before %d rows, After %d rows' % (pcl_feature.shape[0], unique_pcl_feature.shape[0]))        
    pcl_feature = unique_pcl_feature
    
    #top1_percent = 0.01
    accuracy = 0.0
    data_amount = 0.0
    #dist_array = np.zeros([img_feature.shape[0],pcl_feature.shape[0]])

    img_vec = np.sum(np.multiply(img_feature, img_feature), axis=1, keepdims=True)
    pcl_vec = np.sum(np.multiply(pcl_feature, pcl_feature), axis=1, keepdims=True)
    dist_array = img_vec + np.transpose(pcl_vec) - 2*np.matmul(img_feature, np.transpose(pcl_feature))
    
    # record data
    np.savetxt('img_feature.txt',img_feature[:, 0:30],'%.3f')
    np.savetxt('pcl_feature.txt',pcl_feature[:, 0:30],'%.3f')
    np.savetxt('dist_array.txt',dist_array[0:30, 0:45],'%.3f')
    
    # image feature dist
    img_feature_dist = img_vec + np.transpose(img_vec) - 2*np.matmul(img_feature, np.transpose(img_feature))
    np.savetxt('img_feature_dist_array.txt', img_feature_dist[0:30, 0:45], '%.2f')
    
    top1_percent = int(dist_array.shape[1] * 0.01) 

    for i in range(dist_array.shape[0]):
        #if i % 2000 == 0:
            #print('      progress %d' % i, end='\r')
        gt_dist = dist_array[i, index[i]]
        prediction = np.sum(dist_array[i, :] < gt_dist)
        if prediction < top1_percent:
            accuracy += 1.0
        data_amount += 1.0
    accuracy /= data_amount
    
    return accuracy
  

def train(load_version, train_list, test_list):
    print ('-----------------  START to train  -----------------')
    
    
    data = Data(batch_size, image_size, pcl_size, 
                   train_list, test_list[0][1])
    
    # record test_list for checking
    with open('test_list.txt', 'w') as file:
        for line in test_list[0][1]:
            file.writelines('%s %s %s %s\n' % (line.submap_id,line.cam_id, line.sift_filename,line.iss_filename))
    
    # define placeholder
    image_pl   = tf.placeholder(tf.float32, shape=[batch_size, image_size, image_size, 3])
    pos_pcl_pl = tf.placeholder(tf.float32, shape=[batch_size, pcl_size, 3])
    neg_pcl_pl = tf.placeholder(tf.float32, shape=[batch_size, pcl_size, 3])
    
    #pos_label_pl = tf.placeholder(tf.float32, shape=[batch_size, 2])
    #neg_label_pl = tf.placeholder(tf.float32, shape=[batch_size, 2])
    
    label_1 = np.ones((batch_size,1), dtype=np.float32)
    label_0 = np.zeros((batch_size,1),dtype=np.float32)
    pos_label = np.concatenate((label_1,label_0), axis=1)
    neg_label = np.concatenate((label_0, label_1), axis=1)
    
    is_training = tf.placeholder(tf.bool)
    
    #label_pl      = tf.placeholder(tf.int32  , shape=[batch_size, 1])
    learning_rate = tf.placeholder(tf.float32)
    # tensorboard: visualise sift image patch
    tf.summary.image('input_sift_image', image_pl, 64)
    
    # build model
    print ('build model')
    with tf.device('/gpu:1'):   # use gpu 1 to forward
        with tf.variable_scope('image_branch') as scope:
            image_feature = vgg16(image_pl, is_training=True, output_dim=image_feature_dim,
                                  bn_decay=None)
        
        with tf.variable_scope('pointcloud_branch') as scope:
            pos_pcl_feature,_ = pointNet(pos_pcl_pl, pcl_feature_dim, is_training=is_training, 
                                       use_bn=False, bn_decay=None)
            scope.reuse_variables()
            neg_pcl_feature,_ = pointNet(neg_pcl_pl, pcl_feature_dim, is_training=is_training, 
                                       use_bn=False, bn_decay=None)

        img_pos_feature = tf.concat([image_feature, pos_pcl_feature], 1)
        img_neg_feature = tf.concat([image_feature, neg_pcl_feature], 1)
        
        with tf.variable_scope('metric_net') as scope:
            img_pos_pcl_feature = metricNet(img_pos_feature, is_training=is_training, output_dim=2, bn_decay=None)
            scope.reuse_variables()
            img_neg_pcl_feature = metricNet(img_neg_feature, is_training=is_training, output_dim=2, bn_decay=None)
          
    # define loss
    print('define loss...')    
    loss = cross_entropy_loss(img_pos_pcl_feature, img_neg_pcl_feature, pos_label, neg_label)
    # loss = triplet_loss(image_feature, pos_pcl_feature, neg_pcl_feature)
    # tensorboard: visualise loss
    tf.summary.scalar('loss', loss)

    # set training
    print('set training...')
    with tf.device('/gpu:0'):    # use gpu 0 to backward
        # set global step
        global_step = tf.Variable(0, trainable=False)
        # set learning optimisation
        with tf.name_scope('train'):
            train_step = tf.train.AdamOptimizer(learning_rate, 0.9, 0.999).minimize(loss, global_step=global_step)

    saver = tf.train.Saver(tf.all_variables())  # tf.global_variables

    for v in tf.global_variables():
        print('\'%s\',' % v.name)
    exit(0)

    # run model
    print('run model...')
    config = tf.ConfigProto(log_device_placement=False, allow_soft_placement=True)
    config.gpu_options.allow_growth = True
    config.gpu_options.per_process_gpu_memory_fraction = 0.9
    with tf.Session(config=config) as sess:
        # summary
        print('initialise tensorboard...')
        merged = tf.summary.merge_all()
        save_version = 'v2'
        train_writer = tf.summary.FileWriter('tensorboard/' + save_version + '/train', sess.graph)
        test_writer = tf.summary.FileWriter('tensorboard/' + save_version + '/test')

        print('initialise model...')
        sess.run(tf.global_variables_initializer())
        print('   load model...')
        save_path = 'model/' + 'v2' + '/' + load_version + '_model.ckpt'
        saver.restore(sess, save_path)
        #restore_tf_model(sess)
        print("   Model loaded from: %s" % save_path)

        # Train and Test
        global_step_val = 0
        for epoch in range(epoch_time):   
            num_of_iterations = 0          
            
            
            # --------------------- evaluate model ---------------------------
            print('**** Validate ...')
            print('   Compute image and pcl descriptors')
            
            # test the first run /test_list[0]  only
            total_test_num = (len(test_list[0][1]) // batch_size) * batch_size
            
            img_feature = np.zeros([total_test_num, image_feature_dim])
            pcl_feature = np.zeros([total_test_num, pcl_feature_dim])
            
            batch_counter = 0
            
            # feed test list into network
            while True:
                # read a batch
                img_batch, pcl_batch = data.getTestBatch()
                # return None, end of this epoch
                if img_batch is None:
                    break    
                
                # feed batch into network
                feed_dict = {image_pl: img_batch, pos_pcl_pl: pcl_batch, is_training: False}
                img_batch_feature, pcl_batch_feature = sess.run([image_feature, pos_pcl_feature], feed_dict=feed_dict) 
                img_feature[batch_counter: batch_counter+img_batch_feature.shape[0],:] = img_batch_feature
                pcl_feature[batch_counter: batch_counter+pcl_batch_feature.shape[0],:] = pcl_batch_feature
                
                batch_counter += img_batch_feature.shape[0]
                
            print('   Compute top 1 accuracy')
            # compute top1 accuracy and record data
            val_accuracy = ComputeAccuracy(img_feature, pcl_feature)
            with open('tensorboard/'  + 'v2' + 'v1_accuracy.txt', 'a') as file:
                file.write(str(epoch) + ' ' + str(global_step_val) + ' : ' + str(val_accuracy)+'\n')
            print('   global step: %d, accuracy = %.3f%%' % (global_step_val, val_accuracy*100.0))
            # ----------------------------------------------------------------
            
            
            # --------------------- train model ----------------------
            # shuffle train list
            data.train_list = shuffleTrainset(train_list)
            
            while True:
                # read a batch
                img_batch, pos_pcl_batch, neg_pcl_batch = data.getTrainBatch()
                # return None, end of this epoch
                if img_batch is None:
                    break

                global_step_val = tf.train.global_step(sess, global_step)

                feed_dict = {image_pl: img_batch, pos_pcl_pl: pos_pcl_batch, neg_pcl_pl: neg_pcl_batch, 
                             learning_rate: learning_rate_val, is_training: True}
                
                if num_of_iterations % 20 == 0:
                    summary_val, _, loss_val = \
                        sess.run([merged, train_step, loss], feed_dict=feed_dict)
                    print('   global %d, epoch %d, iter %d: loss: %.4f' %
                          (global_step_val, epoch, num_of_iterations, loss_val))
                    # tensorboard: add training information
                    train_writer.add_summary(summary_val, global_step_val)
                else:
                    sess.run(train_step, feed_dict=feed_dict)

                # increment number of iterations
                num_of_iterations += 1
                
                if num_of_iterations % 3000 == 0:
                    # save model
                    save_version = 'v1_' + str(epoch) + '_' + str(num_of_iterations)
                    save_path = saver.save(sess, 'model/v2' + '/' + save_version + '_model.ckpt')
                    print("   Model saved in file: %s" % save_path)
                    
                    # -------------------- evaluate model ---------------------
                    print('**** Validate ...')
                    print('   Compute image and pcl descriptors')
                    
                    # test the first run /test_lists[0]  only
                    total_test_num = (len(test_list[0][1]) // batch_size) * batch_size
                    
                    img_feature = np.zeros([total_test_num, image_feature_dim])
                    pcl_feature = np.zeros([total_test_num, pcl_feature_dim])
                    
                    batch_counter = 0
                    
                    # feed test list into network
                    while True:
                        # read a batch
                        img_batch, pcl_batch = data.getTestBatch()
                        # return None, end of this epoch
                        if img_batch is None:
                            break    
                        
                        # feed batch into network
                        feed_dict = {image_pl: img_batch, pos_pcl_pl: pcl_batch, is_training: False}
                        img_batch_feature, pcl_batch_feature = sess.run([image_feature, pos_pcl_feature], feed_dict=feed_dict) 
                        img_feature[batch_counter: batch_counter+img_batch_feature.shape[0],:] = img_batch_feature
                        pcl_feature[batch_counter: batch_counter+pcl_batch_feature.shape[0],:] = pcl_batch_feature
                        
                        batch_counter += img_batch_feature.shape[0]
                        
                    print('   Compute top 1 accuracy')
                    # compute top1 accuracy and record data
                    val_accuracy = ComputeAccuracy(img_feature, pcl_feature)
                    with open('tensorboard/'  + 'v2'+'v1_accuracy.txt', 'a') as file:
                        file.write(str(epoch) + ' ' + str(global_step_val) + ' : ' + str(val_accuracy)+'\n')
                    print('   global step: %d, accuracy = %.3f%%' % (global_step_val, val_accuracy*100.0))
                    # ---------------------------------------------------------
            
        # tensorboard: close tensorboard files
        train_writer.close()
        test_writer.close()
  
    
if __name__ == '__main__':
    
    #load_version = 'v1_1'
    load_version = 'v2_0_21000'
    #save_version = 'v2'
    #version = 'v1'
    dataset_dir = '/media/mengdan/data3/robotcar/grasshopper/txt_files'
    
    train_list, test_list = splitTrainTest(dataset_dir)
    
    train(load_version, train_list, test_list)
    