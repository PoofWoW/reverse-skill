export ARCHS = arm64 arm64e
export TARGET = iphone:clang:16.5:15.0
export THEOS_PACKAGE_SCHEME = rootless

# ONLY SpringBoard injection. The receiver remains an independent package so
# installing a full candidate never overwrites its baseline test application.
SUBPROJECTS = zxtouch-binary zxtouch-runner pccontrol

include $(THEOS)/makefiles/common.mk
include $(THEOS_MAKE_PATH)/aggregate.mk

after-install::
	install.exec "chown -R mobile:mobile /var/mobile/Library/ZXTouch && killall -9 SpringBoard;"

ifeq ($(ZX_TOUCH_DIAGNOSTICS),1)
after-stage::
	mkdir -p "$(THEOS_STAGING_DIR)/usr/share/zxtouch/diagnostics"
	cp diagnostics/touch-probe.html diagnostics/mixed_touch.py "$(THEOS_STAGING_DIR)/usr/share/zxtouch/diagnostics/"
	find "$(THEOS_STAGING_DIR)" -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -f "$(THEOS_STAGING_DIR)/DEBIAN/postinst-roothide"

before-package::
	python3 tools/label_touch_control.py "$(THEOS_STAGING_DIR)/DEBIAN/control"
endif
