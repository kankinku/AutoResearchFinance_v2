@echo off
setlocal
node "%~dp0node_modules\tsx\dist\cli.mjs" "%~dp0src\cli\index.ts" %*
