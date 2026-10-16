@echo off
cd /d "%~dp0frontend"
echo ========================================================
echo  🚀 Starting BESTBRAND High-Performance Storefront...
echo  🌐 Live connected to WooCommerce and SMART GestCaisse
echo ========================================================
npm.cmd run dev -- --host 127.0.0.1 --port 3000
pause
