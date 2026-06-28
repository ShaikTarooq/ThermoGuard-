# ThermoGuard🌡️

A Flask-based Smart UPS Temperature Monitoring and Climate Control System designed to monitor real-time temperature conditions, automate cooling mechanisms, and provide insightful analytics for UPS rooms and server environments. ThermoGuard helps prevent overheating by intelligently controlling cooling devices and delivering live monitoring through a modern web dashboard.

## 🚀 Features

* **Secure User Authentication:** Login-based access with session management.
* **Real-Time Monitoring:** Live temperature and humidity updates with an animated dashboard.
* **Automatic Climate Control:** Smart fan and air conditioner activation based on configurable temperature thresholds.
* **Interactive Analytics:** Dynamic charts displaying temperature trends, humidity variations, and system performance.
* **Event & Alert Logging:** Records fan/AC operations, warning events, and critical temperature alerts.
* **Historical Data Tracking:** Search, filter, and export historical sensor readings.
* **Configurable Settings:** Customize sensor names, threshold values, temperature units, and automatic control behavior.
* **Responsive Enterprise Dashboard:** Modern Azure-inspired interface optimized for desktop and mobile devices.

## 🛠️ Tech Stack

* **Frontend:** HTML5, CSS3, JavaScript, Chart.js
* **Backend:** Python, Flask
* **Database:** SQLite
* **Visualization:** Chart.js
* **Simulation:** Real-time thermal monitoring with automated cooling logic

## ⚙️ How to Run Locally

1. Make sure **Python 3.10+** is installed.
2. Clone this repository or download the project files.
3. Open a terminal in the project folder.
4. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```
5. Start the Flask application:

   ```bash
   python app.py
   ```
6. Open your browser and navigate to:

   ```
   http://127.0.0.1:5000
   ```

*Note: The application automatically initializes the SQLite database, creates a default administrator account, and starts a real-time temperature simulation on first launch.*
