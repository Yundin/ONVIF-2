# coding=UTF-8
from onvif import ONVIFCamera
import urllib2
import requests
import cv2
import matplotlib.pyplot as plt
import time
from threading import Thread
import numpy

def draw_axis(axis, vals, color):
	axis.cla()
	axis.plot(vals, color)
	axis.set_xlim(0, 255)
	axis.set_yticklabels([])

def calc_move(values, coef, accur, max_step):
	values = [i[0] for i in values]
	if values[0] >= values[1]:
		_max = 0
		_min = 1
		move_to = 1
	else:
		_max = 1
		_min = 0
		move_to = -1
	if values[_max] * accur > values[_min]:
		move = (1 - (values[_min] / values[_max])) * coef * max_step
		move *= move_to
		return move
	return 0

def createImagingRequest(imaging, token):
	requestSetImagingSettings = imaging.create_type("SetImagingSettings")
	requestSetImagingSettings.VideoSourceToken = token
	requestSetImagingSettings.ImagingSettings = imaging.GetImagingSettings({'VideoSourceToken': token})
	return requestSetImagingSettings

def setContrast(imaging, token, value):
	request = createImagingRequest(imaging, token)
	request.ImagingSettings.Contrast = relativeSum(0, 100, value, request.ImagingSettings.Contrast)
	imaging.SetImagingSettings(request)

def setBrightness(imaging, token, value):
	request = createImagingRequest(imaging, token)
	request.ImagingSettings.Brightness = relativeSum(0, 100, value, request.ImagingSettings.Brightness)
	imaging.SetImagingSettings(request)

def setExposure(imaging, token, value):
	request = createImagingRequest(imaging, token)
	try:
		request.ImagingSettings.Exposure.Gain = relativeSum(0, 100, value, request.ImagingSettings.Exposure.Gain)
		imaging.SetImagingSettings(request)
	except Exception as e:
		setBrightness(imaging, token, value)

def setExposureTime(imaging, token, value):
	request = createImagingRequest(imaging, token)
	request.ImagingSettings.Exposure.ExposureTime = relativeSum(0, 40000, value, request.ImagingSettings.Exposure.ExposureTime)
	imaging.SetImagingSettings(request)

def setCrGain(imaging, token, value):
	request = createImagingRequest(imaging, token)
	request.ImagingSettings.WhiteBalance.CrGain = relativeSum(0, 255, value, request.ImagingSettings.WhiteBalance.CrGain)
	imaging.SetImagingSettings(request)

def setCbGain(imaging, token, value):
	request = createImagingRequest(imaging, token)
	request.ImagingSettings.WhiteBalance.CbGain = relativeSum(0, 255, value, request.ImagingSettings.WhiteBalance.CbGain)
	imaging.SetImagingSettings(request)

def relativeSum(minVal, maxVal, relVal, curVal):
	curVal += relVal
	if(curVal < minVal):
		return minVal
	if(curVal > maxVal):
		return maxVal
	return curVal

def isNeedToStop(array):
	perc = numpy.percentile(array, [5, 95])
	need = perc[0] > 200 and perc[0] < 750 and perc[1] < 40000 and perc[1] > 15000
	print need
	return need


# получение сервисов
mycam = ONVIFCamera('192.168.15.42', 80, 'admin', 'Supervisor', '/etc/onvif/wsdl')
media_service = mycam.create_media_service()
media_profile = media_service.GetProfiles()[0]
imaging = mycam.create_imaging_service()
token = media_profile.VideoSourceConfiguration.SourceToken

# установка ручного режима экспозиции и баланса белого
request = createImagingRequest(imaging, token)
try:
	request.ImagingSettings.Exposure.Mode = 'MANUAL'
except Exception as e:
	print 'err'
try:
	request.ImagingSettings.WhiteBalance.Mode = 'MANUAL'
except Exception as e:
	print 'err'
try:
	imaging.SetImagingSettings(request)
except Exception as e:
	print 'err'

# подготовка окна для гистограм
y_ax = plt.subplot(121)
cb_ax = plt.subplot(222)
cr_ax = plt.subplot(224)
plt.ion()
plt.show()

# некоторые камеры имеют слишком большой шаг яркости, эти переменные позволяют до него добраться
plusExposure = 0
minusExposure = 0
while True:
	# авторизация и получение Snapshot
	previewUri = media_service.GetSnapshotUri({'ProfileToken': media_profile._token}).Uri
	login = 'admin'
	password = 'Supervisor'

	manager = urllib2.HTTPPasswordMgrWithDefaultRealm()
	manager.add_password(None, previewUri, login, password)

	auth = urllib2.HTTPBasicAuthHandler(manager)

	opener = urllib2.build_opener(auth)
	urllib2.install_opener(opener)
	image_on_web = urllib2.urlopen(previewUri)
	buf = image_on_web.read()
	filename = "img.jpg"
	downloaded_image = open(filename, "wb")
	downloaded_image.write(buf)
	downloaded_image.close()
	image_on_web.close()

	im = cv2.imread('img.jpg')

	# перевод картинки в YCbCr для удобства
	ycbcr = cv2.cvtColor(im, cv2.COLOR_BGR2YCrCb)

	# составление и отрисовка гистограм
	hist_y = cv2.calcHist([ycbcr],[0],None,[256],[0,256])
	hist_cr = cv2.calcHist([ycbcr],[1],None,[256],[0,256])
	hist_cb = cv2.calcHist([ycbcr],[2],None,[256],[0,256])

	draw_axis(y_ax, hist_y, 'b')
	draw_axis(cb_ax, hist_cb, 'b')
	draw_axis(cr_ax, hist_cr, 'r')
	plt.pause(0.01)

	# вспомогательные гистограммы из 2 точек для цветности
	hist_cb_2 = cv2.calcHist([ycbcr],[2],None,[2],[0,256])
	hist_cr_2 = cv2.calcHist([ycbcr],[1],None,[2],[0,256])

	# вспомогательная гистограмма из 6 точек для яркости
	hist_y_6 = cv2.calcHist([ycbcr], [0], None, [6], [0,256])

	if not isNeedToStop(hist_y):
		# определяем, как далеко слева и справа находяся первые существенные участки гистограммы
		b = len(hist_y_6) - 2
		w = 1
		for i in range(2, len(hist_y_6)):
			if hist_y_6[i][0] > 250000:
				b = i
				break
		for i in range(len(hist_y_6) - 3, 0, -1):
			if hist_y_6[i][0] > 250000:
				w = i
				break
		# определяем, есть ли превышение допустимых значений на краях
		black = hist_y_6[0][0] > 250000
		white = hist_y_6[-1][0] > 250000
		if black and white:
			# и слева и справа слишком большие значения, уменьшаем контрастность
			val = max(hist_y_6[0][0], hist_y_6[-1][0])
			dif = val / 2000000.0 * 20.0
			dif = round(dif)
			print('contrast -', dif)
			setContrast(imaging, token, -dif)
			plusExposure = 0
			minusExposure = 0
		elif black:
			# слишком большое значение только слева, увеличиваем яркость
			dif = (len(hist_y_6) - w - 1) * 10.0 / len(hist_y_6)
			dif = round(dif) + plusExposure
			print('exp +', dif)
			setExposure(imaging, token, dif)
			plusExposure += 1
			minusExposure = 0
		elif white:
			# слишком большое значение только справа, уменьшаем яркость
			dif = b * 10.0 / len(hist_y_6)
			dif = round(dif) + minusExposure
			print('exp -', dif)
			setExposure(imaging, token, -dif)
			plusExposure = 0
			minusExposure += 1
		else:
			# значения на границах небольшие, увеличиваем контрастность
			val = min(b, len(hist_y_6) - w - 1)
			dif = val * 20.0 / (len(hist_y_6) / 2.0)
			dif = round(dif)
			print('contrast +', dif)
			setContrast(imaging, token, dif)
			plusExposure = 0
			minusExposure = 0

	try:
		# пытаемся поместить Cb и Cr по центру гистограммы
		Cb = calc_move(hist_cb_2, 2.56, 0.9, 2)
		Cb = round(Cb)
		print('Cb:', Cb)
		if Cb != 0:
			setCbGain(imaging, token, Cb)
		Cr = calc_move(hist_cr_2, 2.56, 0.9, 2)
		Cr = round(Cr)
		print('Cr:', Cr)
		if Cr != 0:
			setCrGain(imaging, token, Cr)
	except Exception as e:
		print 'WhiteBalance err'

	# некоторые камеры не сразу обновляют snapshot, секунда обычно достаточно
	time.sleep(1)
