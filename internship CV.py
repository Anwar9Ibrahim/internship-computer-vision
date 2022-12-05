#!/usr/bin/env python
# coding: utf-8

# In[6]:


import cv2
import math


# In[7]:


# Import the os module
import os

# Get the current working directory
cwd = os.getcwd()
cwd


# In[8]:


#os.mkdir("test_internship")
os.chdir('test_internship')


# In[22]:


capture= cv2.VideoCapture("cam.mp4")

if( capture.isOpened()== False):
    print("error")

count= 0
counter= 15
while(capture.isOpened()):
    success, frame= capture.read()
    if(success==True):
        #get one frame only every 15 frames
        if (counter==0):
            #cv2.imwrite("frame%d.jpg" % count,frame)
            print(counter, count, "saved")
            count+=1
            #crop the image
            croppedImage= frame[115:350,210:445]
            #resize images
            resizedImage= cv2.resize(croppedImage, dsize=(116,116))
            cv2.imwrite("cropped%d.jpg" % count,resizedImage)
            counter=15
        elif (counter !=0):
            counter-= 1
            #print("skipped", counter)
    else:
        break
        
# When everything done, release the video capture object
capture.release()


# In[ ]:




