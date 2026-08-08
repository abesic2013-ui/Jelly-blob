[app]
title = Jelly Blob
package.name = jellyblob
package.domain = org.tinker

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,wav

version = 1.0

requirements = python3,kivy

orientation = portrait
fullscreen = 0

android.permissions = VIBRATE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a,armeabi-v7a

p4a.bootstrap = sdl2

log_level = 2
warn_on_root = 1
