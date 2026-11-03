<?php $isDev = false; ?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Larkfield Partners — Advisory</title>
<!-- ДЕФЕКТ (favicon): лінк веде на файл, якого у вітці немає -->
<link rel="icon" href="/favicon.ico" type="image/x-icon">
<link rel="stylesheet" href="assets/css/style.css">
</head>
<body>

<header class="site-header">
  <a class="logo" href="./"><span class="logo-mark">L</span> Larkfield</a>
  <nav class="main-nav">
    <a href="./">Home</a>
    <!-- ДЕФЕКТ (empty_href): лінк нікуди не веде -->
    <a href="">Services</a>
    <a href="contact.php">Contact</a>
  </nav>
</header>

<main>
  <section class="hero">
    <h1>Advisory for companies in motion</h1>
    <!-- ДЕФЕКТ (візуальні): контраст 1.9:1 — сірий текст на білому -->
    <p class="hero-sub">We plan, finance and scale mid-sized businesses.</p>
    <a class="btn" href="contact.php">Request a call</a>
  </section>

  <section class="form-wrap">
    <h2>Quick request</h2>
    <!-- ДЕФЕКТ (forms): робоча форма на вайті — є action і method -->
    <form action="/send.php" method="post">
      <label for="name">Name</label>
      <input type="text" id="name" name="name" placeholder="Your name">

      <label for="email">Email</label>
      <input type="email" id="email" name="email" placeholder="you@example.com">

      <button type="submit" class="btn">Send</button>
    </form>
  </section>
</main>

<footer class="site-footer">
  <p>Larkfield Partners</p>
  <!-- ДЕФЕКТ (wrong_literal): {{DOMAIN_NAME}} — це бренд без зони,
       тож info@{{DOMAIN_NAME}} розкриється в неіснуючу адресу -->
  <p>Email: <a href="mailto:info@{{DOMAIN_NAME}}">info@{{DOMAIN_NAME}}</a></p>
  <!-- ДЕФЕКТ (contacts): реальний домен у пошті замість {{DOMAIN}} -->
  <p>Support: <a href="mailto:support@larkfield-partners.com">support@larkfield-partners.com</a></p>
  <p>&copy; 2026 Larkfield Partners.</p>
</footer>

</body>
</html>
