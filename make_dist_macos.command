APP_NAME=SSHFS-Mounter
APP_ICON=resources/app.icns

# cleanup
rm -f -R dist/$APP_NAME/ 2>/dev/null
rm -f -R dist/$APP_NAME.app 2>/dev/null
rm dist/$APP_NAME-macos.zip 2>/dev/null
rm dist/$APP_NAME.dmg 2>/dev/null

pyinstaller SSHFS-Mounter.spec

# copy stuff
cp bin/sshfs dist/$APP_NAME.app/Contents/MacOS/
cp bin/sshpass dist/$APP_NAME.app/Contents/MacOS/

# optimze
rm -R dist/$APP_NAME.app/Contents/Frameworks/libcrypto.3.dylib
rm -R dist/$APP_NAME.app/Contents/Frameworks/libssl.3.dylib
rm -R dist/$APP_NAME.app/Contents/Resources/libcrypto.3.dylib
rm -R dist/$APP_NAME.app/Contents/Resources/libssl.3.dylib

rm -f -R dist/$APP_NAME/

# zip the app
cd dist
zip -q -r $APP_NAME-macos.zip $APP_NAME.app
cd ..

# create compressed DMG
mkdir dist/dmg
mv dist/$APP_NAME.app dist/dmg/
python3 make_dmg.py "dist/dmg" "dist/$APP_NAME.dmg" "$APP_NAME"
mv dist/dmg/$APP_NAME.app dist/
rm -R dist/dmg
