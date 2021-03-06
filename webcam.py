from imutils.video import VideoStream
import cv2
import dlib
import numpy as np
import multiprocessing

import torch
from torch.autograd import Variable


def faceAlignment(img, detector, shapePredictor):
    # Find bounding boxes
    dets = detector(img, 0)

    num_faces = len(dets)
    if num_faces == 0:
        return [], []

    # Find face landmarks we need to do the alignment.
    faces = dlib.full_object_detections()
    frames = []
    for d in dets:
        faces.append(shapePredictor(img, d))
        frames.append([(d.left(), d.top()), (d.right(), d.bottom())])

    # Get the aligned face images
    # Optionally:
    # images = dlib.get_face_chips(img, faces, size=160, padding=0.25)
    imagesAligned = []
    images = dlib.get_face_chips(img, faces, size=320)
    for i, image in enumerate(images):
        #cv_bgr_img = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        image = cv2.resize(image, (256, 256), interpolation=cv2.INTER_LINEAR)
        imagesAligned.append(image)

    # cv2.destroyAllWindows()

    return imagesAligned, frames


# Captures a single image from the camera and returns it in PIL format
def getImage(camera):
    # read is the easiest way to get a full image out of a VideoCapture object.
    retval, im = camera.read()
    return im


def takeSingleImage(cameraPort, adjustmentFrames=30):
    # Initialize camera
    camera = cv2.VideoCapture(cameraPort)

    # Discard frames while camera adjusts to light condition
    for i in range(adjustmentFrames):
        temp = getImage(camera)

    print("Taking image...")
    # Take the actual image we want to keep
    image = getImage(camera)

    del(camera)
    return image


def runSingleImage(cameraPort, modelPath, predictorPath):
    # Preload
    model = torch.load(modelPath)
    model.cpu()
    model.eval()
    detector = dlib.get_frontal_face_detector()
    shapePredictor = dlib.shape_predictor(predictorPath)

    image = takeSingleImage(cameraPort)

    imagesAligned, frames = faceAlignment(image, detector, shapePredictor)

    runCNN(imagesAligned[0], model)

    cv2.imshow('Emotion Classification', imagesAligned[0])
    cv2.waitKey(0)


def runRealtimeStream(cameraPort, modelPath, predictorPath, numProcesses=4, maxFaces=5):
    # Preload
    model = None
    try:
        model = torch.load(modelPath)
    except:
        model = torch.load(modelPath, map_location=lambda storage, loc: storage)

    model.cpu()
    model.eval()
    detector = dlib.get_frontal_face_detector()
    shapePredictor = dlib.shape_predictor(predictorPath)

    # Display window
    cv2.namedWindow("Emotion Classification", 0)
    vc = VideoStream(cameraPort, usePiCamera=0, resolution=(1024, 574)).start()

    manager = multiprocessing.Manager()
    results = manager.list()
    numRunningProc = manager.Value('i', 0)
    for i in range(maxFaces):
        results.append([0, None])

    while True:
        image = vc.read()

        # Detect faces
        imagesAligned, frames = faceAlignment(image, detector, shapePredictor)

        # Create CNN processes
        for i in range(len(frames)):
            if i >= maxFaces:
                break

            if results[i][0] == 0 or numRunningProc.value < numProcesses:
                numRunningProc.value = numRunningProc.value + 1
                results[i] = [results[i][0] + 1] + results[i][1:]
                p = multiprocessing.Process(target=runCNN, args=(imagesAligned[i], model, i, results, numRunningProc))
                p.start()

        # Add rectangle and text
        for i in range(len(frames)):
            if results[i][1] != None:
                cv2.rectangle(image, frames[i][0], frames[i][1], (1, 1, 255))
                text = createDisplayText(results[i][1:])
                cv2.putText(image, text[0], (frames[i][1][0], frames[i][0][1] + 25), 0, 0.7, (1, 1, 255))
                cv2.putText(image, text[1], (frames[i][1][0], frames[i][0][1] + 45), 0, 0.7, (1, 1, 255))
                cv2.putText(image, text[2], (frames[i][1][0], frames[i][0][1] + 65), 0, 0.7, (1, 1, 255))

        cv2.imshow("Emotion Classification", image)

        # ESC to exit
        key = cv2.waitKey(20)
        if key == 27:
            break

    cv2.destroyWindow("Emotion Classification")


def runCNN(img, model, faceId, results, numRunningProc):
    img = img[np.newaxis, :, :, :]
    img = Variable(torch.Tensor(img.astype(float)))
    img = img.permute(0, 3, 1, 2)

    out = model.forward(img).data.numpy()

    # Get results
    emotions = np.argsort(-out)[0]
    percentages = -np.sort(-out)[0]
    tempResults = [results[faceId][0] - 1]

    for i in range(3):
        tempResults.append((emotions[i], percentages[i] - percentages[-1]))

    numRunningProc.value = numRunningProc.value - 1
    results[faceId] = tempResults


def createDisplayText(results):
    emotions = {0: 'neutral', 1: 'happy', 2: 'sad', 3: 'surprise', 4: 'fear', 5: 'disgust', 6: 'anger', 7: 'contempt'}
    totalScore = sum([res[1] for res in results if res != None])
    text = []

    text.append("%s: %0.1f%%" % (emotions[results[0][0]], (results[0][1] / totalScore) * 100))
    text.append("%s: %0.1f%%" % (emotions[results[1][0]], (results[1][1] / totalScore) * 100))
    text.append("%s: %0.1f%%" % (emotions[results[2][0]], (results[2][1] / totalScore) * 100))

    return text


if __name__ == "__main__":
    # WSettings
    cameraPort = 0
    numProcesses = 0
    maxFaces = 5
    modelPath = "models/model_2018-02-04_22-55-40_e9.model"
    predictorPath = "data/shape_predictor_68_face_landmarks.dat"

    #runSingleImage(cameraPort, modelPath, predictorPath, emotions)
    runRealtimeStream(cameraPort, modelPath, predictorPath, numProcesses, maxFaces)
