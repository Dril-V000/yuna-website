/* YUNA Reviews — reads reviews.json and draws review cards */
(function () {
  'use strict';

  // ===== الإعدادات (يمكنك تغييرها) =====
  const JSON_URL = './reviews.json';   // مسار ملف التقييمات
  const CONTAINER_ID = 'reviews';      // اسم المكان في index.html
  const TITLE = 'What our users say';
  const SUBTITLE = 'Real feedback from real users.';
  // =====================================

  const container = document.getElementById(CONTAINER_ID);
  if (!container) return; // إن لم تضع المكان في الصفحة لا يفعل شيئاً

  // ---------- التنسيق ----------
  const css = `
  .rv-section{padding:6rem 2rem;background:var(--bg2,#07071a)}
  .rv-head{text-align:center}
  .rv-tag{display:inline-block;background:rgba(167,139,250,.1);border:1px solid rgba(167,139,250,.25);color:var(--accent2,#a78bfa);font-size:.73rem;font-weight:700;padding:.28rem .85rem;border-radius:100px;margin-bottom:1rem;letter-spacing:1.5px;text-transform:uppercase}
  .rv-title{font-size:clamp(1.9rem,4vw,3rem);font-weight:800;color:var(--text,#eef1ff);margin-bottom:.8rem}
  .rv-sub{color:var(--text2,#9aa3cc);margin:0 auto;max-width:520px}
  .rv-avg{margin-top:1rem;color:#fbbf24;font-weight:700}
  .rv-avg span{color:var(--text2,#9aa3cc);font-weight:500;font-size:.85rem}
  .rv-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:1.4rem;max-width:1000px;margin:3rem auto 0}
  .rv-card{display:flex;flex-direction:column;background:var(--card,#0d0d1f);border:1px solid var(--border,rgba(110,150,255,.1));border-radius:16px;padding:1.5rem;transition:all .3s}
  .rv-card:hover{border-color:var(--border2,rgba(110,150,255,.25));transform:translateY(-4px)}
  .rv-stars{color:#fbbf24;font-size:1.15rem;letter-spacing:2px;margin-bottom:.6rem}
  .rv-text{flex:1;font-size:.9rem;color:var(--text2,#9aa3cc);font-style:italic;line-height:1.7;margin-bottom:1.2rem}
  .rv-author{display:flex;align-items:center;gap:.8rem}
  .rv-avatar{width:38px;height:38px;border-radius:50%;background:var(--grad-main,linear-gradient(135deg,#64b5f6,#a78bfa));display:flex;align-items:center;justify-content:center;font-weight:800;color:#04040c}
  .rv-name{font-weight:700;font-size:.88rem;color:var(--text,#eef1ff)}
  .rv-role{font-size:.72rem;color:var(--text3,#5a6390)}
  .rv-btn{margin-top:1rem;background:rgba(100,181,246,.1);border:1px solid var(--border2,rgba(110,150,255,.25));color:var(--accent3,#7dd3fc);padding:.45rem 1rem;border-radius:9px;font-weight:700;font-size:.78rem;cursor:pointer}
  .rv-btn:hover{background:rgba(100,181,246,.2)}
  .rv-modal{display:none;position:fixed;inset:0;z-index:9999;background:rgba(4,4,12,.93);align-items:center;justify-content:center;padding:2rem;cursor:zoom-out}
  .rv-modal.open{display:flex}
  .rv-modal img{max-width:900px;width:100%;max-height:90vh;object-fit:contain;border-radius:14px;border:1px solid rgba(110,150,255,.25)}
  @media(max-width:820px){.rv-section{padding:4rem 1.3rem}}
  `;
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  // ---------- دوال مساعدة ----------
  // تصنع عنصراً (وسم) بنص آمن
  function make(tag, className, text) {
    const e = document.createElement(tag);
    if (className) e.className = className;
    if (text !== undefined) e.textContent = text; // textContent = آمن، لا ينفّذ أي كود
    return e;
  }

  // يقبل فقط مسارات الصور الآمنة
  function safeImage(url) {
    if (typeof url !== 'string') return null;
    if (url.startsWith('./') || url.startsWith('/') || url.startsWith('https://')) return url;
    return null;
  }

  function starsText(n) {
    const s = Math.min(5, Math.max(1, Math.round(Number(n) || 5)));
    return '★'.repeat(s) + '☆'.repeat(5 - s);
  }

  // ---------- نافذة الصورة ----------
  const modal = make('div', 'rv-modal');
  const modalImg = make('img');
  modalImg.alt = 'Review screenshot';
  modal.appendChild(modalImg);
  modal.addEventListener('click', () => modal.classList.remove('open'));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') modal.classList.remove('open');
  });
  document.body.appendChild(modal);

  // ---------- بناء بطاقة تقييم ----------
  function buildCard(r) {
    const card = make('div', 'rv-card');
    card.appendChild(make('div', 'rv-stars', starsText(r.stars)));
    card.appendChild(make('p', 'rv-text', '"' + (r.text || '') + '"'));

    const author = make('div', 'rv-author');
    const name = String(r.name || 'User');
    author.appendChild(make('div', 'rv-avatar', name.charAt(0).toUpperCase()));
    const info = make('div');
    info.appendChild(make('div', 'rv-name', name));
    info.appendChild(make('div', 'rv-role', r.role || 'Verified User'));
    author.appendChild(info);
    card.appendChild(author);

    const img = safeImage(r.screenshot);
    if (img) {
      const btn = make('button', 'rv-btn', 'View screenshot 📸');
      btn.type = 'button';
      btn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        modalImg.src = img;
        modal.classList.add('open');
      });
      card.appendChild(btn);
    }
    return card;
  }

  // ---------- تحميل وعرض ----------
  async function init() {
    try {
      const res = await fetch(JSON_URL, { cache: 'no-store' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      const list = Array.isArray(data) ? data : (data.reviews || []);

      // لا توجد تقييمات = لا يظهر القسم
      if (!list.length) return;

      const section = make('section', 'rv-section');

      const head = make('div', 'rv-head');
      head.appendChild(make('div', 'rv-tag', 'Community Reviews'));
      head.appendChild(make('h2', 'rv-title', TITLE));
      head.appendChild(make('p', 'rv-sub', SUBTITLE));

      const avg = list.reduce((s, r) => s + (Number(r.stars) || 5), 0) / list.length;
      const avgBox = make('div', 'rv-avg', '★ ' + avg.toFixed(1) + ' ');
      avgBox.appendChild(make('span', '', '(' + list.length + ' reviews)'));
      head.appendChild(avgBox);
      section.appendChild(head);

      const grid = make('div', 'rv-grid');
      list.forEach((r) => grid.appendChild(buildCard(r)));
      section.appendChild(grid);

      container.appendChild(section);
    } catch (err) {
      console.warn('[Reviews] could not load reviews.json:', err);
      // عند الخطأ يبقى المكان فارغاً ولا يكسر الصفحة
    }
  }

  init();
})();