"""Перевіряє, що стандартні php-скрипти вайта відповідають еталону.

Три еталонні скрипти: init-блок (autoload/dotenv/returnPage/trackingConfig),
підключення пікселів у <head> (fb + gtag) і конверсійний блок у <body>.
Порівняння йде по фрагментах з нормалізацією: пробіли схлопуються, імена
змінних ($isDev, $returnPage, …) знеособлюються, дефолт WHITE_FORM_RETURN_PAGE
('thank-you' тощо) замінюється плейсхолдером — тобто інша назва сторінки чи
перейменована змінна не вважаються помилкою, а зміна логіки — вважається.
"""
import re
from pathlib import Path

import checks.form_stub as _form_stub

NAME = "PHP-скрипти: відповідність еталону"
DESCRIPTION = ("Звіряє init-блок, підключення пікселів (fb/gtag) і конверсійний "
               "блок index.php з еталоном; назви змінних і дефолтна return page "
               "не порівнюються.")
FILES = ["*.php"]
GROUP = "review"
PROJECTS = ["php"]

# дефолт WHITE_FORM_RETURN_PAGE → плейсхолдер (щоб 'thank-you'/'obrigado'/… не порівнювались)
RX_PAGE = re.compile(r"(WHITE_FORM_RETURN_PAGE['\"]\]\s*\?\?\s*)['\"][^'\"]*['\"]")
# $змінні → $V (суперглобали $_GET/$_ENV/… починаються з "_" і не чіпаються)
RX_VAR = re.compile(r"\$(?!_)\w+")


def _prep(code: str) -> str:
    code = RX_PAGE.sub(r"\1'<PAGE>'", code)
    code = RX_VAR.sub("$V", code)
    return re.sub(r"\s+", " ", code).strip()


# (назва блоку, якір для пошуку рядка у файлі, еталонний код)
_RAW_FRAGMENTS = [
    ("init: isDev + autoload/dotenv", r"vendor/autoload\.php", """
$isDev = false;
if(!$isDev) {
    require_once __DIR__ . '/../vendor/autoload.php';
    $dotenv = Dotenv\\Dotenv::createImmutable(__DIR__ . '/landings/');
    $dotenv->safeLoad();
}
"""),
    ("init: returnPage", r"WHITE_FORM_RETURN_PAGE", """
$returnPage = $_ENV['WHITE_FORM_RETURN_PAGE'] ?? 'thank-you';
if (!str_ends_with($returnPage, '.html')) {
    $returnPage .= '.html';
}
"""),
    ("init: trackingConfig", r"GA4_MEASUREMENT_ID", """
$trackingConfig = [
    'gtagId'      => $_ENV['GA4_MEASUREMENT_ID'] ?? null,
    'gtagCLabel'  => $_ENV['GOOGLE_CONVERSION_LABEL'] ?? null,
    'bingPixelId' => $_ENV['BING_PIXEL_ID'] ?? null,
    'fbPixelId'   => $_ENV['FB_PIXEL_ID'] ?? null
];
"""),
    ("init: fbpixelevent", r"fbpixelevent", """
$facebookPixelEventLeadKey = null;
if (!empty($_GET['fbpixelevent']) || !empty($_ENV['FB_EVENT_NAME'])) {
    $facebookPixelEventLeadKey = $_GET['fbpixelevent'] ?? $_ENV['FB_EVENT_NAME'];
}
"""),
    ("head: fb pixel loader", r"fbq\('init'", """
<?php if(!empty($trackingConfig['fbPixelId'])): ?>
<script>
   !function (f, b, e, v, n, t, s) {
      if (f.fbq) return;
      n = f.fbq = function () {
            n.callMethod ?
            n.callMethod.apply(n, arguments) : n.queue.push(arguments)
      };
      if (!f._fbq) f._fbq = n;
      n.push = n;
      n.loaded = !0;
      n.version = '2.0';
      n.queue = [];
      t = b.createElement(e);
      t.async = !0;
      t.src = v;
      s = b.getElementsByTagName(e)[0];
      s.parentNode.insertBefore(t, s)
   }(window, document, 'script', 'https://connect.facebook.net/en_US/fbevents.js');
   fbq('init', '<?= $trackingConfig['fbPixelId'] ?>');
   fbq('track', 'PageView');
</script>
<?php endif; ?>
"""),
    ("head: gtag loader", r"gtag\('config'", """
<?php if(!empty($trackingConfig['gtagId'])): ?>
<script src="https://www.googletagmanager.com/gtag/js?id=<?= $trackingConfig['gtagId'] ?>"></script>
<script>
   window.dataLayer = window.dataLayer || [];
   function gtag(){dataLayer.push(arguments);}
   gtag('js', new Date());
   gtag('config', '<?= $trackingConfig['gtagId'] ?>');
</script>
<?php endif; ?>
"""),
    ("body: параметри ліда з $_GET", r"isset\(\$_GET\['email'\]\)", """
if (isset($_GET['email']) || isset($_GET['name'])) {
   $email = $_GET['email'] ?? '';
   $name = $_GET['name'] ?? '';
   $phone = ltrim('+', $_GET['phone'] ?? '');
   $lastname = $_GET['lastname'] ?? '';
"""),
    ("body: fb lead event", r"\bem:\s*'", """
   if(!empty($trackingConfig['fbPixelId'])) {
      echo <<<EOL
      <script>
         fbq('track', '$facebookPixelEventLeadKey', {
            em: '$email',
            fn: '$name',
            ln: '$lastname',
            ph: '$phone',
         });
      </script>
EOL;
   }
"""),
    ("body: gtag conversion", r"'send_to'", """
   if(!empty($trackingConfig['gtagId']) && !empty($trackingConfig['gtagCLabel'])) {
      $gtagId = $trackingConfig['gtagId'];
      $gtagCLabel = $trackingConfig['gtagCLabel'];
      echo <<<EOL
      <script>
         gtag('event', 'conversion', {'send_to': '$gtagId/$gtagCLabel'});
         var head = document.head || document.getElementsByTagName('head')[0];
         var scriptsElement = document.createElement('script');
         scriptsElement.innerHTML = "gtag('event', 'conversion', {'send_to': '$gtagId/$gtagCLabel'});";
         head.appendChild(scriptsElement);
      </script>
EOL;
   }
"""),
    ("body: bing pixel", r"new UET\(", """
   if(!empty($trackingConfig['bingPixelId'])) {
      $bingPixelId = $trackingConfig['bingPixelId'];
      echo <<<EOL
      <script>
         (function(w, d, t, r, u) {
            var f, n, i;
            w[u] = w[u] || [], f = function() {
                  var o = {
                     ti: '$bingPixelId',
                     enableAutoSpaTracking: true
                  };
                  o.q = w[u], w[u] = new UET(o), w[u].push("pageLoad")
            }, n = d.createElement(t), n.src = r, n.async = 1, n.onload = n.onreadystatechange = function() {
                  var s = this.readyState;
                  s && s !== "loaded" && s !== "complete" || (f(), n.onload = n.onreadystatechange = null)
            }, i = d.getElementsByTagName(t)[0], i.parentNode.insertBefore(n, i)
         })(window, document, "script", "//bat.bing.com/bat.js", "uetq");
      </script>
EOL;
   }
"""),
    ("body: redirect на return page + exit", r"window\.location\.href", """
   echo <<<EOL
   <script>
      setTimeout( () => {
         window.location.href = '/$returnPage';
      }, 500)
   </script>
EOL;
   exit();
}
"""),
]

FRAGMENTS = [(label, re.compile(anchor), _prep(code))
             for label, anchor, code in _RAW_FRAGMENTS]

# файл вважаємо "вхідним" (з обов'язковими скриптами), якщо це index.php
# або в ньому вже є сліди цих скриптів
_MARKERS = ("WHITE_FORM_RETURN_PAGE", "GA4_MEASUREMENT_ID",
            "fbevents.js", "$trackingConfig")


def run(path, text):
    if _form_stub.is_stubbed(text) or _form_stub.is_lead_cut(text):
        return []                       # форма-заглушка (form_stub): лід не перехоплюється свідомо;
                                        # або лід-PHP зрізано, а сама форма — на сторінці контактів
    is_index = Path(path).name.lower() == "index.php"
    has_marker = any(m in text for m in _MARKERS)
    if not is_index and not has_marker:
        return []

    if is_index and not has_marker:
        return [{"line": 1, "severity": "error",
                 "message": "стандартні php-скрипти (init/пікселі/конверсія) "
                            "відсутні в index.php"}]

    norm = _prep(text)
    issues = []
    for label, anchor, frag in FRAGMENTS:
        if frag in norm:
            continue
        m = anchor.search(text)
        if m:
            line = text[:m.start()].count("\n") + 1
            msg = f"блок «{label}» відрізняється від еталонного"
        else:
            line = None
            msg = f"блок «{label}» відсутній"
        issues.append({"line": line, "severity": "error", "message": msg})
    return issues
