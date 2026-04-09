/** @odoo-module **/

document.addEventListener('keydown', (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && ev.key === 's') {
        const saveBtn = document.querySelector(
            '.o_knowledge_form .o_form_button_save:not([disabled])'
        );
        if (saveBtn) {
            ev.preventDefault();
            saveBtn.click();
        }
    }
});

const QUICK_EMOJIS = [
    '📄','📝','📋','📌','📍','🗂️','📁','📂',
    '📚','📖','📔','📒','📓','📃','📜','📊',
    '🚀','💡','⭐','🎯','✅','❌','⚠️','🔍',
    '👥','👤','🏠','🏢','💼','🔑','🔒','🔓',
    '💻','🖥️','📱','⚙️','🛠️','🔧','🔨','🎉',
    '❤️','💙','💚','💛','🧡','💜','🖤','🤍',
];

function showEmojiPicker(inputEl) {
    const old = document.querySelector('.o_knowledge_emoji_picker');
    if (old) old.remove();

    const picker = document.createElement('div');
    picker.className = 'o_knowledge_emoji_picker';
    picker.style.cssText = [
        'position:fixed',
        'z-index:99999',
        'background:white',
        'border:1px solid #dee2e6',
        'border-radius:12px',
        'padding:10px',
        'box-shadow:0 8px 32px rgba(0,0,0,0.15)',
        'display:grid',
        'grid-template-columns:repeat(8,1fr)',
        'gap:2px',
        'max-width:300px',
    ].join(';');

    QUICK_EMOJIS.forEach(emoji => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = emoji;
        btn.style.cssText = 'font-size:1rem;background:none;border:none;border-radius:6px;cursor:pointer;padding:3px;line-height:1';
        btn.addEventListener('mouseover', () => { btn.style.background = '#f0f0f0'; });
        btn.addEventListener('mouseout',  () => { btn.style.background = 'none'; });
        btn.addEventListener('mousedown', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            setter.call(inputEl, emoji);
            inputEl.dispatchEvent(new Event('input',  { bubbles: true }));
            inputEl.dispatchEvent(new Event('change', { bubbles: true }));
            picker.remove();
        });
        picker.appendChild(btn);
    });

    const rect = inputEl.getBoundingClientRect();
    picker.style.top  = (rect.bottom + 4) + 'px';
    picker.style.left = rect.left + 'px';
    document.body.appendChild(picker);

    setTimeout(() => {
        document.addEventListener('mousedown', function close(e) {
            if (!picker.contains(e.target) && e.target !== inputEl) {
                picker.remove();
                document.removeEventListener('mousedown', close);
            }
        });
    }, 100);
}

function initEmojiPicker(root) {
    (root || document).querySelectorAll('.o_knowledge_icon_field input').forEach(input => {
        if (input.dataset.kbEmojiInit) return;
        input.dataset.kbEmojiInit = '1';
        input.addEventListener('focus', () => showEmojiPicker(input));
    });
}

const _observer = new MutationObserver(() => {
    if (document.querySelector('.o_knowledge_icon_field:not([data-kb-emoji-init])')) {
        initEmojiPicker();
    }
});

document.addEventListener('DOMContentLoaded', () => {
    _observer.observe(document.body, { childList: true, subtree: true });
});