"""Тести form_hijack: JS-перехоплювач submit, який вбиває відправку форми.

Клас із генератора: form.addEventListener('submit', e => { e.preventDefault();
…валідація…; window.location.href='thank-you.html'; }) — форма ВИГЛЯДАЄ
робочою (валідація, редірект на подяку), але дані нікуди не відправляються.

Правило: submit-хендлер шкідливий, якщо в ньому є preventDefault І редірект,
але НЕМАЄ жодної відправки (fetch/XHR/axios/sendBeacon/form.submit()).
Фікс коментує хендлер маркерами, щоб правку можна було відкотити.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                              # noqa: E402

mod = load_check("form_hijack")

# зразок користувача (один із трьох — вони відрізняються лише суфіксами імен)
SAMPLE = """function _zpc(){
    var forms=document.querySelectorAll('.ujuo');
    for(var f=0;f<forms.length;f++){ (function(form){
      function field(n){ return form.querySelector('[name="'+n+'"]'); }
      function _ygh(n){ return form.querySelector('[data-error="'+n+'"]'); }
      function setErr(n,on){ var e=_ygh(n); if(e){ e.classList.toggle('is-visible',!!on); } }
      ['name','phone','consent'].forEach(function(n){ var el=field(n); if(el){ el.addEventListener('input',function(){setErr(n,false);}); el.addEventListener('change',function(){setErr(n,false);}); } });
      try{
        var qs=new URLSearchParams(window.location.search);
        ['utm_source','utm_medium','utm_campaign','gclid'].forEach(function(k){ var h=field(k); var v=_xaz(qs,k); if(h&&v){ h.value=v; } });
      }catch(e){}
      form.addEventListener('submit',function(e){
        e.preventDefault();
        var hp=field('website'); if(hp&&hp.value.trim()!==''){ return; }
        var ok=true;
        var name=field('name'), phone=field('phone'), cons=field('consent');
        if(!name||name.value.trim().replace(/[^A-Za-z\\u00c0-\\u024f\\u0400-\\u04ff]/g,'').length<2){ setErr('name',true); ok=false; }
        if(!phone||phone.value.replace(/\\D/g,'').length<7){ setErr('phone',true); ok=false; }
        if(!cons||!cons.checked){ setErr('consent',true); ok=false; }
        if(ok){ window.location.href='thank-you.html'; }
      });
    })(forms[f]); }
  }
"""


# ------------------------------------------------------------------ детекція
def test_sample_hijacker_is_flagged():
    issues = mod.run("js/main.js", SAMPLE)
    assert len(issues) == 1, issues
    assert issues[0]["severity"] == "error"
    assert issues[0]["line"] == 12, "рядок самого addEventListener('submit')"


def test_three_handlers_three_issues():
    text = SAMPLE + SAMPLE.replace("_zpc", "_bcr").replace(".ujuo", ".uphn") \
                  + SAMPLE.replace("_zpc", "_apm").replace(".ujuo", ".ujaq")
    assert len(mod.run("js/main.js", text)) == 3


def test_corpus_variant_with_email_regex_is_flagged():
    """Реальний варіант з кешу: інші поля, і regex `/^[^\\s@]+@…$/.test()`
    усередині — сканер не має заблукати в літералі."""
    text = """form.addEventListener('submit',function(e){
      e.preventDefault(); var ok=true;
      var email=field('email');
      if(!email||!/^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/.test(email.value)){ setErr('email','Bad'); ok=false; }
      if(ok){ window.location.href='thank-you.html'; }
    });"""
    assert len(mod.run("js/main.js", text)) == 1


def test_regex_with_parens_inside_does_not_break_balance():
    text = """form.addEventListener('submit',function(e){
      e.preventDefault();
      var v=x.replace(/[()]/g,'');
      window.location.href='thank-you.html';
    });
    tail();"""
    issues = mod.run("js/main.js", text)
    assert len(issues) == 1
    fixed = mod.fix("js/main.js", text)
    assert "tail();" in fixed and not fixed.strip().startswith("/*") or "tail();" in fixed


def test_double_quoted_submit_and_location_assign():
    text = 'form.addEventListener("submit",function(e){e.preventDefault();location.assign("thank-you.html");});'
    assert len(mod.run("js/main.js", text)) == 1


# ------------------------------------------------------------------ винятки
def test_ajax_submit_is_legit():
    """Інжектований скрипт форми робить preventDefault + fetch + редірект —
    він ВІДПРАВЛЯЄ дані, чіпати його не можна."""
    text = """form.addEventListener('submit', function(e){
      e.preventDefault();
      fetch('/lead.php', {method:'POST', body:new FormData(form)})
        .then(function(){ window.location.href='thank-you.html'; });
    });"""
    assert mod.run("js/main.js", text) == []


def test_native_resubmit_is_legit():
    """Валідація з подальшим form.submit() — форма таки відправляється."""
    text = """form.addEventListener('submit', function(e){
      e.preventDefault();
      if(valid(form)){ form.submit(); } else { window.location.href='#err'; }
    });"""
    assert mod.run("js/main.js", text) == []


def test_prevent_without_redirect_not_flagged():
    """Без редіректу доказ неповний (може відправляти через невидиму нам
    функцію) — консервативно пропускаємо."""
    text = "form.addEventListener('submit',function(e){e.preventDefault();doStuff(form);});"
    assert mod.run("js/main.js", text) == []


def test_click_handler_not_flagged():
    text = "btn.addEventListener('click',function(e){e.preventDefault();window.location.href='x.html';});"
    assert mod.run("js/main.js", text) == []


def test_submit_without_prevent_not_flagged():
    text = "form.addEventListener('submit',function(e){ga('send','event');});"
    assert mod.run("js/main.js", text) == []


# ------------------------------------------------------------------ фікс
def test_fix_comments_out_and_becomes_clean():
    fixed = mod.fix("js/main.js", SAMPLE)
    assert mod.OPEN_MARK in fixed and mod.CLOSE_MARK in fixed
    assert mod.run("js/main.js", fixed) == [], "закоментоване не має ловитись удруге"
    # решта функції жива: UTM-заповнення і слухачі полів не чіпаються
    assert "URLSearchParams" in fixed.split(mod.OPEN_MARK)[0]


def test_fix_is_revertible_byte_exact():
    """Сенс коментування замість видалення: прибрав два маркери — отримав
    байт-у-байт початковий код."""
    fixed = mod.fix("js/main.js", SAMPLE)
    reverted = fixed.replace(mod.OPEN_MARK, "").replace(mod.CLOSE_MARK, "")
    assert reverted == SAMPLE


def test_fix_is_idempotent():
    fixed = mod.fix("js/main.js", SAMPLE)
    assert mod.fix("js/main.js", fixed) == fixed


def test_fix_on_minified_single_line_keeps_neighbors_alive():
    """У мінімізованому js все на одному рядку — блоковий коментар мусить
    вимкнути лише хендлер, а код до і після нього лишити робочим."""
    text = ("var a=1;form.addEventListener('submit',function(e){e.preventDefault();"
            "window.location.href='thank-you.html';});var b=2;")
    fixed = mod.fix("js/main.js", text)
    assert fixed.startswith("var a=1;")
    assert fixed.endswith("var b=2;")
    assert mod.run("js/main.js", fixed) == []


def test_fix_handles_all_three_functions():
    text = SAMPLE + SAMPLE.replace("_zpc", "_bcr") + SAMPLE.replace("_zpc", "_apm")
    fixed = mod.fix("js/main.js", text)
    assert fixed.count(mod.OPEN_MARK) == 3
    assert mod.run("js/main.js", fixed) == []
    reverted = fixed.replace(mod.OPEN_MARK, "").replace(mod.CLOSE_MARK, "")
    assert reverted == text


def test_fix_leaves_legit_ajax_untouched():
    text = """form.addEventListener('submit', function(e){
      e.preventDefault();
      fetch('/lead.php', {method:'POST'}).then(function(){ location.href='ty.html'; });
    });"""
    assert mod.fix("js/main.js", text) == text


def test_already_commented_is_invisible():
    fixed = mod.fix("js/main.js", SAMPLE)
    assert mod.run("js/main.js", fixed) == []
    assert mod.fix("js/main.js", fixed) == fixed


if __name__ == "__main__":
    run(dict(globals()))
