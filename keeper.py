#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔄 كوبرا - نظام إعادة التشغيل التلقائي
يعيد تشغيل البوت تلقائياً عند توقفه
"""

import subprocess
import time
import logging
import sys
import os

logging.basicConfig(
    format='%(asctime)s [KEEPER] %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('keeper.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

BOT_SCRIPT = os.path.join(os.path.dirname(__file__), "bot.py")
RESTART_DELAY = 5  # ثواني قبل إعادة التشغيل

def run():
    restart_count = 0
    while True:
        logger.info(f"🚀 تشغيل البوت... (المحاولة #{restart_count + 1})")
        try:
            proc = subprocess.run(
                [sys.executable, BOT_SCRIPT],
                timeout=None
            )
            exit_code = proc.returncode
            logger.warning(f"⚠️ البوت توقف بكود: {exit_code}")
        except KeyboardInterrupt:
            logger.info("🛑 تم إيقاف البوت يدوياً.")
            break
        except Exception as e:
            logger.error(f"❌ خطأ: {e}")

        restart_count += 1
        logger.info(f"🔄 إعادة التشغيل خلال {RESTART_DELAY} ثانية...")
        time.sleep(RESTART_DELAY)

if __name__ == "__main__":
    run()
