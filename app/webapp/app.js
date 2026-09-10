(() => {
  const tg = window.Telegram?.WebApp;
  const input = document.getElementById('media-url');
  const field = document.getElementById('url-field');
  const submit = document.getElementById('download-button');
  const paste = document.getElementById('paste-button');
  const status = document.getElementById('form-status');
  const platformButtons = [...document.querySelectorAll('.platform')];
  const pageButtons = [...document.querySelectorAll('[data-page-target]')];
  const navButtons = [...document.querySelectorAll('.nav-item')];

  const patterns = [
    { name: 'YouTube', test: /(?:youtube\.com|youtu\.be)/i },
    { name: 'TikTok', test: /(?:tiktok\.com|vm\.tiktok\.com)/i },
    { name: 'Instagram', test: /instagram\.com/i },
    { name: 'X / تويتر', test: /(?:x\.com|twitter\.com)/i },
  ];

  function haptic(style = 'light') {
    try { tg?.HapticFeedback?.impactOccurred(style); } catch (_) { /* optional */ }
  }

  function showPage(name) {
    document.querySelectorAll('.page').forEach(page => {
      page.classList.toggle('active', page.dataset.page === name);
    });
    navButtons.forEach(button => {
      button.classList.toggle('active', button.dataset.pageTarget === name);
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
    haptic();
  }

  function detectPlatform(url) {
    return patterns.find(item => item.test.test(url))?.name || null;
  }

  function selectPlatform(name) {
    platformButtons.forEach(button => {
      button.classList.toggle('selected', button.dataset.platform === name);
    });
  }

  function setStatus(message, isError = false) {
    status.textContent = message;
    status.classList.toggle('error', isError);
    field.classList.toggle('invalid', isError);
  }

  function validUrl(value) {
    try {
      const url = new URL(value);
      return ['http:', 'https:'].includes(url.protocol) && detectPlatform(value);
    } catch (_) {
      return false;
    }
  }

  pageButtons.forEach(button => {
    button.addEventListener('click', () => showPage(button.dataset.pageTarget));
  });

  platformButtons.forEach(button => {
    button.addEventListener('click', () => {
      selectPlatform(button.dataset.platform);
      input.focus();
      setStatus(`جاهز لاستقبال رابط ${button.dataset.platform}`);
      haptic();
    });
  });

  input.addEventListener('input', () => {
    const name = detectPlatform(input.value.trim());
    selectPlatform(name);
    if (input.value.trim() && !name) {
      setStatus('ألصق رابطًا من إحدى المنصات المدعومة', true);
    } else if (name) {
      setStatus(`تم التعرف على ${name} ✓`);
    } else {
      setStatus('يدعم الروابط العامة من المنصات الأربع');
    }
  });

  paste.addEventListener('click', async () => {
    try {
      input.value = await navigator.clipboard.readText();
      input.dispatchEvent(new Event('input'));
      input.focus();
      haptic();
    } catch (_) {
      input.focus();
      setStatus('اضغط مطولًا داخل الحقل للصق الرابط');
    }
  });

  submit.addEventListener('click', () => {
    const url = input.value.trim();
    if (!validUrl(url)) {
      setStatus('تأكد من صحة الرابط وأنه من منصة مدعومة', true);
      haptic('heavy');
      return;
    }
    if (!tg?.sendData) {
      setStatus('افتح هذه الواجهة من زر RABET داخل محادثة البوت', true);
      return;
    }

    submit.disabled = true;
    submit.querySelector('.button-label').textContent = 'جارٍ إرسال الرابط…';
    setStatus('ستعود الآن إلى المحادثة ويبدأ تجهيز المقطع');
    haptic('medium');
    window.setTimeout(() => {
      tg.sendData(JSON.stringify({ action: 'download', url }));
    }, 320);
  });

  if (tg) {
    tg.ready();
    tg.expand();
    try {
      tg.setHeaderColor('#090e1b');
      tg.setBackgroundColor('#090e1b');
      tg.setBottomBarColor('#090e1b');
    } catch (_) { /* older Telegram clients */ }
  }
})();
