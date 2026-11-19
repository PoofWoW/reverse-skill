ARCHS = arm64 arm64e
TARGET = iphone:clang:16.5:15.0
THEOS_PACKAGE_SCHEME = rootless
include $(THEOS)/makefiles/common.mk
APPLICATION_NAME = ZXTouchProbe
ZXTouchProbe_FILES = main.m
ZXTouchProbe_FRAMEWORKS = UIKit CoreGraphics
ZXTouchProbe_CFLAGS = -fobjc-arc
ZXTouchProbe_RESOURCE_FILES = Info.plist
include $(THEOS_MAKE_PATH)/application.mk

before-package::
	chmod -R a+rX "$(THEOS_STAGING_DIR)"
	if [ -d "$(THEOS_STAGING_DIR)tmp" ]; then chmod -R a+rX "$(THEOS_STAGING_DIR)tmp"; fi
