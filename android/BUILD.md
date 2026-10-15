# Android source

End users: the parent folder already contains GalaxyPhoneBridge.apk. You do not need Android Studio.

Developer rebuild: JDK 17, Android SDK Platform 35, Android Build Tools 35.0.0, Gradle 8.9 and Android Gradle Plugin 8.7.3. With those tools installed, run `gradle assembleDebug` from this directory (no Gradle wrapper binary is bundled). Gradle will use your local debug signing key. A different signing key cannot update the delivered APK in place; uninstall only this companion App and re-pair after reinstalling. Keep your signing key private and reuse it for your future updates.

The delivered APK was compiled directly from these Java/XML sources with Eclipse ECJ 3.38.0 (Java 8 bytecode), aapt2 35.0.0, D8 35.0.0, zipalign and apksigner, against android-35_r02/android.jar. No third-party Android runtime libraries. The binary uses a private development signing key, not included in this archive. Source files and APK checksums are included in the parent directory.

Package: hk.jimmy.galaxybridge. The development APK is debuggable solely to allow authorized ADB `run-as` provisioning of its private pairing token. It declares no Internet permission. No gesture injection, screenshot permission, arbitrary shell endpoint or auto-enabling of Accessibility is included.

Protocol: one JSON line per local socket connection to abstract name galaxy_phone_access_v3. Requests contain op and token, plus snapshot_id/node_id for click. Operations: status, ui, click. The companion Python module forwards a random host loopback port via ADB and authenticates every request. Never log tokens or UI contents.
