# JARVIS — Türkçe sesli asistan

Türkçe dinler, Türkçe konuşur, bilgisayarınızı yönetir. Anlamadığı her şeyi
ücretsiz **Gemini** yapay zekasına sorar; Gemini de bilgisayarda iş yapabilir
(dosya, uygulama, PowerShell komutu...). Kamera kullanılmaz.

## Kurulum (Windows)

1. [Python 3.12](https://www.python.org/downloads/) kurun ("Add Python to PATH" işaretli).
2. Bu klasörde **`kur.bat`** dosyasına çift tıklayın.
3. https://aistudio.google.com/apikey adresinden ücretsiz Gemini anahtarı alın,
   klasördeki **`.env`** dosyasını Not Defteri ile açıp `GEMINI_API_KEY=` satırının sonuna yapıştırın.
4. **`baslat.bat`** (sesli) veya **`yazarak_baslat.bat`** (klavyeyle) ile başlatın.

## Örnek komutlar

| Ne | Örnek |
|---|---|
| Saat / tarih | "saat kaç", "bugün günlerden ne" |
| Hava, haber, döviz | "Ankara'da hava nasıl", "haberleri oku", "dolar kaç" |
| Uygulama | "Chrome'u aç", "not defterini aç", "Spotify'ı kapat" |
| Site / arama | "instagram aç", "Google'da python dersleri ara", "YouTube'da Tarkan çal" |
| Ses / ekran | "sesi aç", "sesi kıs", "parlaklığı 40 yap", "ekran görüntüsü al" |
| Not / hatırlatma | "not al süt al", "notlarımı oku", "10 dakika sonra çayı hatırlat" |
| Dosyalar | "masaüstü klasörünü aç", "indirilenler neler var" |
| Klavye | "şunu yaz Merhaba", "kopyala", "yapıştır", "pencere değiştir" |
| Bilgisayar | "bilgisayarı kilitle", "bilgisayarı kapat", "yeniden başlat", "uyku modu" |
| Yapay zeka | "masaüstümdeki pdf dosyalarını bul", "bana bir e-posta taslağı yaz", her türlü soru |
| Çıkış | "görüşürüz" |

Silme, taşıma, kapatma gibi geri alınamaz işlemlerden önce JARVIS "evet" onayı ister.
`.env` içinde `JARVIS_TAM_YETKI=1` yaparsanız sormaz (yanlış duyulan bir cümle dosya silebilir — önerilmez).

---

<h1 align="center">J.A.R.V.I.S </h1> 

<div align="center">
  
[![Welcome to my profile](https://img.shields.io/badge/Hello,Devs!-Welcome-blue.svg?style=flat&logo=github)](https://github.com/gauravsingh9356/J.A.R.V.I.S)
[![Open Source Love](https://badges.frapsoft.com/os/v2/open-source.svg?v=103)](https://github.com/gauravsingh9356/J.A.R.V.I.S)
 [![GitHub issues](https://img.shields.io/github/issues/GauravSingh9356/J.A.R.V.I.S)](https://github.com/GauravSingh9356/J.A.R.V.I.S/issues)
![Stars](https://img.shields.io/github/stars/gauravsingh9356/J.A.R.V.I.S?style=flat&logo=github)
![Forks](https://img.shields.io/github/forks/gauravsingh9356/J.A.R.V.I.S?style=flat&logo=github)
[![GitHub license](https://img.shields.io/github/license/GauravSingh9356/J.A.R.V.I.S)](https://github.com/GauravSingh9356/J.A.R.V.I.S/blob/master/LICENSE)
  
[![forthebadge made-with-python](http://ForTheBadge.com/images/badges/made-with-python.svg)](https://www.python.org/)

  </div>



<img src="jarvis1.jpg"/>

### Requirements:

<li>datetime</li>
<li>os</li>
<li> pyttsx3</li>
<li> wikipedia</li>
<li> speech_recognition </li>
<li> webbrowser</li>
<li> sys</li>
<li> smtplib</li>
<li>requests</li>
<li>json</li>
<li>defflib</li>
<li>geocoder</li>
<li>pyjokes</li>
<li>psutil</li>
<li> pyautogui</li>
<li> opencv</li>

<h2>Required Packages</h2>

```
pip install -r requirements.txt
```

> _ To install PyAudio on windows head over to https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio and download the .whl for your machine and run the installation as shown below, then install the remaining dependencies from the requirements.txt file. You may remove pyAduio from the requirements file if it interrupts your installation (its there for unix users)
```bash
pip install PyAudio‑0.2.11‑cp<version>‑cp<version>m‑win_amd<architecture>.whl
```

### On Ubuntu based Linux distribution you need to install the following packages, so that the code works:

```bash
sudo apt-get update
sudo apt-get install espeak-ng portaudio19-dev tesseract-ocr python3-tk python3-dev scrot
python3 -m venv venv            # needs a Python that has tkinter (python3-tk)
source venv/bin/activate
pip install -r requirements.txt
python jarvis.py
```

### What it does...

  <ul>
   <li>Dynamic Authentication using Optical Face Recognition</li>
<li>Send emails</li>
  <li>Dynamic News Reporting at any time with api integration</li>
  <li>Todo list generator, Yes it remembers all!</li> 
<li>Open any website with just a voice command</li>
<li>Plays Music</li>
<li>Tells time</li>
<li>Wikipedia powered AI</li>
<li>Dictionary with Intelligent Sensing i.e. auto checking if spell mistake</li>
<li>Weather Report such as temp, wind speed, humidity, weather description</li>
<li>Latitude and longitude</li>
 <li>YouTube searching</li> 
 <li>Google Map searching</a>
 <li>YouTube Downloader, download any youtube video by just putting url of video</li>
 <li>Now Master can switch b/w J.A.R.V.I.S and F.R.I.D.A.Y, switch to female voice assistant</li>
</ul>

<table>
  <tr>
    <td><img src="images/Screenshot%20(138).png"/></td>
      <td><img src="https://github.com/GauravSingh9356/J.A.R.V.I.S/blob/master/images/face-600x900.png"/></td>
    

</tr>
<tr>
<td><img src="images/email.jpg"/></td>
<td><img src="https://github.com/GauravSingh9356/J.A.R.V.I.S/blob/master/images/maxresdefault.jpg"/></td>
</tr>
<td><img src="https://github.com/GauravSingh9356/J.A.R.V.I.S/blob/master/images/4-Best-Weather-Forecast-APIs-for-Development-of-Weather-Apps-624x304.jpeg"/></td>
  <td><img src="https://github.com/GauravSingh9356/J.A.R.V.I.S/blob/master/images/maxresdefault%20(1).jpg"/></td>
</tr>
<tr>
  <td><img src="canny.jpg"/>
          </td>
  <td><img src="ImgContor.jpg"/>
          </td>
</tr>
</table>

## Some Sneak peeks:

<ul>
  <li><h2> Jarvis, Are you there?</h2></li>
  <li><h2> At your service, Sir</h2></li>
  
  <li><h2> Jarvis, What are today's news headlines? can you tell?</h2></li>
  <li><h2>Ofcourse, Sir -> Then news headlines   Would you like to visit the news url?</h2></li>
  
  <li><h2> Search Youtube</h2></li>
  <li><h2>What you want to search, Sir</h2></li>
  <li><h2>Coding for kids</h2></li>
  <li><h2> Opens youtube in browser with desired search query results </h2></li>
  
   <li><h2> Jarvis, Can you send email to Gaurav?</h2></li>
  <li><h2>What I say sir, Sir</h2></li>
   <li><h2>Gaurav is a good boy</h2></li>
  <li><h2> Email is sent successfully, Sir</h2></li>
  
  # And so on....
  
<a href="https://techtalkswithgaurav.blogspot.com/2020/06/your-personal-assistant-jarvis.html" target="_blank">Read complete blog article</a>

## Contribution:
Thank you for your interest in contributing to our Repo! Pull requests are welcome. For fixing typos, please make a PR with your fixes. We are happy for every contribution.
A lot can be done with this project. Core AI chatbot like functionality can be added. More python scripts can be associated. Pull requests for any such changes are accepted. Feel free to fork this project and make your own changes too.
