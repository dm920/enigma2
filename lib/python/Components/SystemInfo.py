import re
from hashlib import md5
from types import MappingProxyType
from enigma import Misc_Options, eDVBCIInterfaces, eDVBResourceManager, eGetEnigmaDebugLvl
from Tools.Directories import SCOPE_PLUGINS, fileCheck, fileExists, fileHas, pathExists, resolveFilename

SystemInfo = {}


from Tools.Multiboot import getMultibootStartupDevice, getMultibootslots  # This import needs to be here to avoid a SystemInfo load loop!


class BoxInformation:
	def __init__(self, root=""):
		boxInfoCollector = {}
		self.boxInfoMutable = {}
		boxInfoCollector["checksum"] = None
		checksumcollectionstring = ""
		file = root + "/usr/lib/enigma.info"
		if fileExists(file):
			for line in open(file, 'r').readlines():
				if line.startswith("checksum="):
					boxInfoCollector["checksum"] = md5(bytearray(checksumcollectionstring, "UTF-8", errors="ignore")).hexdigest() == line.strip().split('=')[1]
					break
				checksumcollectionstring += line
				if line.startswith("#") or line.strip() == "":
					continue
				if '=' in line:
					item, value = [x.strip() for x in line.split('=')]
					boxInfoCollector[item] = self.processValue(value)
			if boxInfoCollector["checksum"]:
				print("[SystemInfo] Enigma information file data loaded into BoxInfo.")
			else:
				print("[SystemInfo] Enigma information file data loaded, but checksum failed.")
		else:
			print("[SystemInfo] ERROR: %s is not available!  The system is unlikely to boot or operate correctly." % file)
		self.boxInfo = MappingProxyType(boxInfoCollector)

	def processValue(self, value):
		if value and value[0] in ("\"", "'") and value[-1] == value[0]:
			return value[1:-1]
		else:
			try:
				return eval(value, {"__builtins__": {}}, {})
			except:
				return value

	def getEnigmaInfoList(self):
		return sorted(self.boxInfo.keys())

	def getEnigmaConfList(self):  # not used by us
		return []

	def getItemsList(self):
		return sorted({**self.boxInfo, **self.boxInfoMutable}.keys())

	def getItem(self, item, default=None):
		if item in self.boxInfo:
			return self.boxInfo[item]
		elif item in self.boxInfoMutable:
			return self.boxInfoMutable[item]
		elif item in SystemInfo:
			return SystemInfo[item]
		return default

	def setItem(self, item, value, immutable=False, forceOverride=False):
		print('*', item, value, immutable, forceOverride)
		if item in self.boxInfo and not forceOverride:
			print("[BoxInfo] Error: Item '%s' is immutable and can not be %s!" % (item, "changed" if item in self.boxInfo else "added"))
			return False
		if immutable:
			boxInfoCollector = dict(self.boxInfo)
			boxInfoCollector[item] = value
			self.boxInfo = MappingProxyType(boxInfoCollector)
		else:
			self.boxInfoMutable[item] = value
		return True

	def deleteItem(self, item, forceOverride=False):
		if item in self.boxInfo:
			if forceOverride:
				boxInfoCollector = dict(self.boxInfo)
				del boxInfoCollector[item]
				self.boxInfo = MappingProxyType(boxInfoCollector)
				return True
			else:
				print("[BoxInfo] Error: Item '%s' is immutable and can not be deleted!" % item)
		if item in self.boxInfoMutable:
			del self.boxInfoMutable[item]
			return True


BoxInfo = BoxInformation()


# Parse the boot commandline.
#
with open("/proc/cmdline", "r") as fd:
	cmdline = fd.read()
cmdline = {k: v.strip('"') for k, v in re.findall(r'(\S+)=(".*?"|\S+)', cmdline)}


def getNumVideoDecoders():
	numVideoDecoders = 0
	while fileExists("/dev/dvb/adapter0/video%d" % numVideoDecoders, "f"):
		numVideoDecoders += 1
	return numVideoDecoders


def countFrontpanelLEDs():
	numLeds = fileExists("/proc/stb/fp/led_set_pattern") and 1 or 0
	while fileExists("/proc/stb/fp/led%d_pattern" % numLeds):
		numLeds += 1
	return numLeds


def hassoftcaminstalled():
	from Tools.camcontrol import CamControl
	return len(CamControl("softcam").getList()) > 1


def getBootdevice():
	dev = ("root" in cmdline and cmdline["root"].startswith("/dev/")) and cmdline["root"][5:]
	while dev and not fileExists("/sys/block/%s" % dev):
		dev = dev[:-1]
	return dev


model = BoxInfo.getItem("machine", default="unknown")

SystemInfo["RecoveryMode"] = fileCheck("/proc/stb/fp/boot_mode")
SystemInfo["InDebugMode"] = eGetEnigmaDebugLvl() >= 4
SystemInfo["CommonInterface"] = model in ("h9combo", "h9combose", "h10", "pulse4kmini") and 1 or eDVBCIInterfaces.getInstance().getNumOfSlots()
SystemInfo["CommonInterfaceCIDelay"] = fileCheck("/proc/stb/tsmux/rmx_delay")
for cislot in range(0, SystemInfo["CommonInterface"]):
	SystemInfo["CI%dSupportsHighBitrates" % cislot] = fileCheck("/proc/stb/tsmux/ci%d_tsclk" % cislot)
	SystemInfo["CI%dRelevantPidsRoutingSupport" % cislot] = fileCheck("/proc/stb/tsmux/ci%d_relevant_pids_routing" % cislot)
SystemInfo["HasSoftcamInstalled"] = hassoftcaminstalled()
SystemInfo["NumVideoDecoders"] = getNumVideoDecoders()
SystemInfo["PIPAvailable"] = SystemInfo["NumVideoDecoders"] > 1
SystemInfo["CanMeasureFrontendInputPower"] = eDVBResourceManager.getInstance().canMeasureFrontendInputPower()
SystemInfo["12V_Output"] = Misc_Options.getInstance().detected_12V_output()
SystemInfo["ZapMode"] = fileCheck("/proc/stb/video/zapmode") or fileCheck("/proc/stb/video/zapping_mode")
SystemInfo["HaveTouchSensor"] = model in ("dm900", "dm920")
SystemInfo["NumFrontpanelLEDs"] = countFrontpanelLEDs()
SystemInfo["FrontpanelDisplay"] = fileExists("/dev/dbox/oled0") or fileExists("/dev/dbox/lcd0")
SystemInfo["LCDsymbol_circle_recording"] = fileCheck("/proc/stb/lcd/symbol_circle") or model in ("hd51", "vs1500") and fileCheck("/proc/stb/lcd/symbol_recording")
SystemInfo["LCDsymbol_timeshift"] = fileCheck("/proc/stb/lcd/symbol_timeshift")
SystemInfo["LCDshow_symbols"] = (model.startswith("et9") or model in ("hd51", "vs1500")) and fileCheck("/proc/stb/lcd/show_symbols")
SystemInfo["LCDsymbol_hdd"] = model in ("hd51", "vs1500") and fileCheck("/proc/stb/lcd/symbol_hdd")
SystemInfo["FrontpanelDisplayGrayscale"] = fileExists("/dev/dbox/oled0")
SystemInfo["DeepstandbySupport"] = model != "dm800"
SystemInfo["Fan"] = fileCheck("/proc/stb/fp/fan")
SystemInfo["FanPWM"] = SystemInfo["Fan"] and fileCheck("/proc/stb/fp/fan_pwm")
SystemInfo["PowerLED"] = fileCheck("/proc/stb/power/powerled") or model in ("gbue4k", "gbquad4k") and fileCheck("/proc/stb/fp/led1_pattern")
SystemInfo["StandbyLED"] = fileCheck("/proc/stb/power/standbyled") or model in ("gbue4k", "gbquad4k") and fileCheck("/proc/stb/fp/led0_pattern")
SystemInfo["SuspendLED"] = fileCheck("/proc/stb/power/suspendled") or fileCheck("/proc/stb/fp/enable_led")
SystemInfo["Display"] = SystemInfo["FrontpanelDisplay"] or SystemInfo["StandbyLED"]
SystemInfo["LedPowerColor"] = fileCheck("/proc/stb/fp/ledpowercolor")
SystemInfo["LedStandbyColor"] = fileCheck("/proc/stb/fp/ledstandbycolor")
SystemInfo["LedSuspendColor"] = fileCheck("/proc/stb/fp/ledsuspendledcolor")
SystemInfo["Power4x7On"] = fileCheck("/proc/stb/fp/power4x7on")
SystemInfo["Power4x7Standby"] = fileCheck("/proc/stb/fp/power4x7standby")
SystemInfo["Power4x7Suspend"] = fileCheck("/proc/stb/fp/power4x7suspend")
SystemInfo["PowerOffDisplay"] = model not in "formuler1" and fileCheck("/proc/stb/power/vfd") or fileCheck("/proc/stb/lcd/vfd")
SystemInfo["WakeOnLAN"] = not model.startswith("et8000") and fileCheck("/proc/stb/power/wol") or fileCheck("/proc/stb/fp/wol")
SystemInfo["HasExternalPIP"] = not (model.startswith("et9") or model in ("e4hd",)) and fileCheck("/proc/stb/vmpeg/1/external")
SystemInfo["VideoDestinationConfigurable"] = fileExists("/proc/stb/vmpeg/0/dst_left")
SystemInfo["hasPIPVisibleProc"] = fileCheck("/proc/stb/vmpeg/1/visible")
SystemInfo["MaxPIPSize"] = model in ("hd51", "h7", "vs1500", "e4hd") and (360, 288) or (540, 432)
SystemInfo["VFD_scroll_repeats"] = not model.startswith("et8500") and fileCheck("/proc/stb/lcd/scroll_repeats")
SystemInfo["VFD_scroll_delay"] = not model.startswith("et8500") and fileCheck("/proc/stb/lcd/scroll_delay")
SystemInfo["VFD_initial_scroll_delay"] = not model.startswith("et8500") and fileCheck("/proc/stb/lcd/initial_scroll_delay")
SystemInfo["VFD_final_scroll_delay"] = not model.startswith("et8500") and fileCheck("/proc/stb/lcd/final_scroll_delay")
SystemInfo["LcdLiveTV"] = fileCheck("/proc/stb/fb/sd_detach") or fileCheck("/proc/stb/lcd/live_enable")
SystemInfo["LcdLiveTVMode"] = fileCheck("/proc/stb/lcd/mode")
SystemInfo["LcdLiveDecoder"] = fileCheck("/proc/stb/lcd/live_decoder")
SystemInfo["FastChannelChange"] = False
SystemInfo["3DMode"] = fileCheck("/proc/stb/fb/3dmode") or fileCheck("/proc/stb/fb/primary/3d")
SystemInfo["3DZNorm"] = fileCheck("/proc/stb/fb/znorm") or fileCheck("/proc/stb/fb/primary/zoffset")
SystemInfo["Blindscan_t2_available"] = fileCheck("/proc/stb/info/vumodel") and model.startswith("vu")
SystemInfo["RcTypeChangable"] = not (model in ("gbquad4k", "gbue4k", "et8500") or model.startswith("et7")) and pathExists("/proc/stb/ir/rc/type")
SystemInfo["HasFullHDSkinSupport"] = model not in ("et4000", "et5000", "sh1", "hd500c", "hd1100", "xp1000", "lc")
SystemInfo["HasBypassEdidChecking"] = fileCheck("/proc/stb/hdmi/bypass_edid_checking")
SystemInfo["HasMMC"] = "root" in cmdline and cmdline["root"].startswith("/dev/mmcblk")
SystemInfo["HasColorspace"] = fileCheck("/proc/stb/video/hdmi_colorspace")
SystemInfo["HasColorspaceSimple"] = SystemInfo["HasColorspace"] and SystemInfo["HasMMC"] and SystemInfo["Blindscan_t2_available"]
SystemInfo["HasTranscoding"] = pathExists("/proc/stb/encoder/0") or fileCheck("/dev/bcm_enc0")
SystemInfo["HasH265Encoder"] = fileHas("/proc/stb/encoder/0/vcodec_choices", "h265")
SystemInfo["CanNotDoSimultaneousTranscodeAndPIP"] = model in ("vusolo4k", "gbquad4k", "gbue4k")
SystemInfo["HasColordepth"] = fileCheck("/proc/stb/video/hdmi_colordepth")
SystemInfo["HasFrontDisplayPicon"] = model in ("dm900", "dm920", "et8500", "vusolo4k", "vuuno4kse", "vuduo4k", "vuduo4kse", "vuultimo4k", "gbquad4k", "gbue4k")
SystemInfo["Has24hz"] = fileCheck("/proc/stb/video/videomode_24hz")
SystemInfo["Has2160p"] = fileHas("/proc/stb/video/videomode_preferred", "2160p50")
SystemInfo["HasHDMIpreemphasis"] = fileCheck("/proc/stb/hdmi/preemphasis")
SystemInfo["HasColorimetry"] = fileCheck("/proc/stb/video/hdmi_colorimetry")
SystemInfo["HasHdrType"] = fileCheck("/proc/stb/video/hdmi_hdrtype")
SystemInfo["HasScaler_sharpness"] = pathExists("/proc/stb/vmpeg/0/pep_scaler_sharpness")
SystemInfo["HasHDMIin"] = BoxInfo.getItem("hdmifhdin") or BoxInfo.getItem("hdmihdin")
SystemInfo["HasHDMI-CEC"] = BoxInfo.getItem("hdmi") and fileExists(resolveFilename(SCOPE_PLUGINS, "SystemPlugins/HdmiCEC/plugin.py")) and (fileExists("/dev/cec0") or fileExists("/dev/hdmi_cec") or fileExists("/dev/misc/hdmi_cec0"))
SystemInfo["HasYPbPr"] = model in ("dm8000", "et5000", "et6000", "et6500", "et9000", "et9200", "et9500", "et10000", "formuler1", "mbtwinplus", "spycat", "vusolo", "vuduo", "vuduo2", "vuultimo")
SystemInfo["HasScart"] = model in ("dm8000", "et4000", "et6500", "et8000", "et9000", "et9200", "et9500", "et10000", "formuler1", "hd1100", "hd1200", "hd1265", "hd2400", "vusolo", "vusolo2", "vuduo", "vuduo2", "vuultimo", "vuuno", "xp1000")
SystemInfo["HasSVideo"] = model in ("dm8000")
SystemInfo["HasComposite"] = model not in ("dm900", "dm920", "i55", "gbquad4k", "gbue4k", "hd1500", "osnino", "osninoplus", "purehd", "purehdse", "revo4k", "vusolo4k", "vuzero4k", "vuduo4k", "vuduo4kse", "vuuno4k", "vuuno4kse", "vuultimo4k")
SystemInfo["hasXcoreVFD"] = model in ("osmega", "spycat4k", "spycat4kmini", "spycat4kcombo") and fileCheck("/sys/module/brcmstb_%s/parameters/pt6302_cgram" % model)
SystemInfo["HasOfflineDecoding"] = model not in ("osmini", "osminiplus", "et7000mini", "et11000", "mbmicro", "mbtwinplus", "mbmicrov2", "et7000", "et8500")
SystemInfo["hasKexec"] = fileHas("/proc/cmdline", "kexec=1")
SystemInfo["canKexec"] = not SystemInfo["hasKexec"] and fileExists("/usr/bin/kernel_auto.bin") and fileExists("/usr/bin/STARTUP.cpio.gz") and (model in ("vuduo4k", "vuduo4kse") and ["mmcblk0p9", "mmcblk0p6"] or model in ("vusolo4k", "vuultimo4k", "vuuno4k", "vuuno4kse") and ["mmcblk0p4", "mmcblk0p1"] or model == "vuzero4k" and ["mmcblk0p7", "mmcblk0p4"])
SystemInfo["MultibootStartupDevice"] = getMultibootStartupDevice()
SystemInfo["canMode12"] = "%s_4.boxmode" % model in cmdline and cmdline["%s_4.boxmode" % model] in ("1", "12") and "192M"
SystemInfo["canMultiBoot"] = getMultibootslots()
SystemInfo["canDualBoot"] = fileExists("/dev/block/by-name/flag")
SystemInfo["canFlashWithOfgwrite"] = not (model.startswith("dm"))
SystemInfo["HDRSupport"] = fileExists("/proc/stb/hdmi/hlg_support_choices") and fileCheck("/proc/stb/hdmi/hlg_support")
SystemInfo["CanProc"] = SystemInfo["HasMMC"] and not SystemInfo["Blindscan_t2_available"]
SystemInfo["HasMultichannelPCM"] = fileCheck("/proc/stb/audio/multichannel_pcm")
SystemInfo["HasAutoVolume"] = fileExists("/proc/stb/audio/avl_choices") and fileCheck("/proc/stb/audio/avl")
SystemInfo["HasAutoVolumeLevel"] = fileExists("/proc/stb/audio/autovolumelevel_choices") and fileCheck("/proc/stb/audio/autovolumelevel")
SystemInfo["Has3DSurround"] = fileExists("/proc/stb/audio/3d_surround_choices") and fileCheck("/proc/stb/audio/3d_surround")
SystemInfo["Has3DSpeaker"] = fileExists("/proc/stb/audio/3d_surround_speaker_position_choices") and fileCheck("/proc/stb/audio/3d_surround_speaker_position")
SystemInfo["Has3DSurroundSpeaker"] = fileExists("/proc/stb/audio/3dsurround_choices") and fileCheck("/proc/stb/audio/3dsurround")
SystemInfo["Has3DSurroundSoftLimiter"] = fileExists("/proc/stb/audio/3dsurround_softlimiter_choices") and fileCheck("/proc/stb/audio/3dsurround_softlimiter")
SystemInfo["DreamBoxAudio"] = model in ("dm900", "dm920")
SystemInfo["CanDownmixAC3"] = fileHas("/proc/stb/audio/ac3_choices", "downmix")
SystemInfo["CanDownmixDTS"] = fileHas("/proc/stb/audio/dts_choices", "downmix")
SystemInfo["CanDownmixAAC"] = fileHas("/proc/stb/audio/aac_choices", "downmix")
SystemInfo["HDMIAudioSource"] = fileCheck("/proc/stb/hdmi/audio_source")
SystemInfo["CanAC3Transcode"] = fileHas("/proc/stb/audio/ac3plus_choices", "force_ac3")
SystemInfo["CanDTSHD"] = fileHas("/proc/stb/audio/dtshd_choices", "downmix")
SystemInfo["CanDownmixAACPlus"] = fileHas("/proc/stb/audio/aacplus_choices", "downmix")
SystemInfo["CanAACTranscode"] = fileHas("/proc/stb/audio/aac_transcode_choices", "off")
SystemInfo["CanWMAPRO"] = fileHas("/proc/stb/audio/wmapro_choices", "downmix")
SystemInfo["CanBTAudio"] = fileHas("/proc/stb/audio/btaudio_choices", "off")
SystemInfo["CanBTAudioDelay"] = fileCheck("/proc/stb/audio/btaudio_delay") or fileCheck("/proc/stb/audio/btaudio_delay_pcm")
SystemInfo["BootDevice"] = getBootdevice()
SystemInfo["NimExceptionVuSolo2"] = model == "vusolo2"
SystemInfo["NimExceptionVuDuo2"] = model == "vuduo2"
SystemInfo["NimExceptionDMM8000"] = model == "dm8000"
SystemInfo["FbcTunerPowerAlwaysOn"] = model in ("dm900", "dm920", "vusolo4k", "vuduo4k", "vuduo4kse", "vuultimo4k", "vuuno4k", "vuuno4kse")
SystemInfo["HasPhysicalLoopthrough"] = ["Vuplus DVB-S NIM(AVL2108)", "GIGA DVB-S2 NIM (Internal)"]
if model in ("et7500", "et8500"):
	SystemInfo["HasPhysicalLoopthrough"].append("AVL6211")
SystemInfo["HasFBCtuner"] = ["Vuplus DVB-C NIM(BCM3158)", "Vuplus DVB-C NIM(BCM3148)", "Vuplus DVB-S NIM(7376 FBC)", "Vuplus DVB-S NIM(45308X FBC)", "Vuplus DVB-S NIM(45208 FBC)", "DVB-S2 NIM(45208 FBC)", "DVB-S2X NIM(45308X FBC)", "DVB-S2 NIM(45308 FBC)", "DVB-C NIM(3128 FBC)", "BCM45208", "BCM45308X", "BCM3158"]
SystemInfo["HasHiSi"] = pathExists("/proc/hisi")
SystemInfo["FCCactive"] = False
SystemInfo["Autoresolution_proc_videomode"] = model in ("gbue4k", "gbquad4k") and "/proc/stb/video/videomode_50hz" or "/proc/stb/video/videomode"
