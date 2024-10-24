# Secure-Access-Streamlit-Dashboard
Custom Streamlit dashboard for Cisco Secure Access

This project was created to address specific needs but can also serve as a **baseline** for building custom **Streamlit dashboards** that interact with Cisco Secure Access APIs. The dashboards in this repository provide a framework for visualizing data related to user enrollment, VPN connections, and ZTNA activity.

## **Features**

- **User Enrollment Dashboard**: Displays data from ZTNA APIs, showing statistics on users with active, expired, or revoked devices.
- **VPN Connections Dashboard**: Shows information about VPN user connections (Machine Tunnels), including device names, public IPs, assigned IPs, login times, and connection durations.
- **ZTNA Activity Dashboard**: Visualizes Zero Trust Network Access (ZTNA) activity, showing top accessed private resources and identifying resources for the current day since 5 AM Mexico City time.

## **Prerequisites**

Before you start, make sure you have the following installed:

- **Python 3.7+**
- **Streamlit**
- **Pandas**
- **Plotly**
- **Requests**
- **Pillow**
- **Pytz**

## **Setup Instructions**

1. **Clone the repository**:
   ```bash
   git clone https://github.com/tavomed/Secure-Access-Streamlit-Dashboard.git
   cd Secure-Access-Streamlit-Dashboard
   ```

2. **Install dependencies**:
   Use the `requirements.txt` file to install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set API Credentials and Logos**:
   - Replace the following values in the code with your actual Cisco Secure Access API key and secret:
   ```python
   api_key = "your_api_key"
   key_secret = "your_api_secret"
   ```

   - Add your logos (such as `logo1.png` and `logo2.png`) to the project folder, and make sure they are correctly referenced in the code:
   ```python
   logo1 = Image.open("logo1.png")
   logo2 = Image.open("logo2.png")
   ```

4. **Run the Streamlit app**:
   Start the Streamlit dashboard by running:
   ```bash
   streamlit run DASHBOARD.py
   ```

5. **Access the dashboard**:
   Open your web browser and navigate to `http://localhost:8501` to view the dashboard.

## **Environment Variables (Optional)**

To avoid hardcoding the API key, secret, and logo paths, you can set them as environment variables:

### **API Key and Secret**:
```bash
export API_KEY="your-api-key"
export API_SECRET="your-api-secret"
```

Then update the code to use the environment variables:
```python
api_key = os.getenv('API_KEY')
key_secret = os.getenv('API_SECRET')
```

### **Logos Path**:
You can also specify the path for logos as environment variables:
```bash
export LOGO1_PATH="path/to/logo1.png"
export LOGO2_PATH="path/to/logo2.png"
```

Then update the code to dynamically load logos:
```python
logo1 = Image.open(os.getenv('LOGO1_PATH'))
logo2 = Image.open(os.getenv('LOGO2_PATH'))
```

## **Dashboards**

### **1. User Enrollment Dashboard**
   - Displays the number of Active Directory users.
   - Shows enrolled users with active, expired, or revoked devices.
   - Includes a detailed user enrollment progress bar.

### **2. VPN Connections Dashboard (Machine Tunnels)**
   - Fetches and visualizes VPN user connections.
   - Displays login time, active session duration, and public/assigned IPs.

### **3. ZTNA Activity Dashboard**
   - Shows top accessed private resources and resources without activity since 5 AM.
   - Displays graphs for interactive exploration of ZTNA data.

## **API Documentation**

This project interacts with Cisco Secure Access APIs. You can find the API documentation and more details [here](https://developer.cisco.com/docs/cloud-security/secure-access-api-getting-started/).

## **Author**

This project was created by **Gustavo Medina** to meet specific organizational needs but is designed to be flexible and serve as a **baseline** for others looking to build custom dashboards with **Streamlit** and the Cisco Secure Access APIs.

