<?php $isDev = false; ?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Contact — Northgate Consulting</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="assets/css/style.css">
</head>
<body>

<header class="site-header">
  <a class="logo" href="./"><span class="logo-mark">N</span> Northgate</a>
  <nav class="main-nav">
    <a href="./">Home</a>
    <a href="services.php">Services</a>
    <a href="contact.php">Contact</a>
  </nav>
</header>

<main>
  <section class="hero">
    <h1>Contact us</h1>
    <p>Tell us what you are working on and we will get back within one business day.</p>
  </section>

  <section class="form-wrap">
    <form>
      <label for="name">Name</label>
      <input type="text" id="name" name="name" placeholder="Your name">

      <label for="email">Email</label>
      <input type="email" id="email" name="email" placeholder="you@example.com">

      <label for="message">Message</label>
      <textarea id="message" name="message" rows="5" placeholder="How can we help?"></textarea>

      <button type="submit" class="btn">Send request</button>
    </form>
  </section>
</main>

<footer class="site-footer">
  <p>Northgate Consulting</p>
  <p>Email: <a href="mailto:info@{{DOMAIN}}">info@{{DOMAIN}}</a></p>
  <p>&copy; 2026 Northgate Consulting. All rights reserved.</p>
</footer>

</body>
</html>
