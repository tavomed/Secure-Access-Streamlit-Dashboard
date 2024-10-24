import streamlit as st
import pandas as pd
import requests
import time
import json
import os
from datetime import datetime, timedelta
import pytz
import plotly.express as px
from collections import Counter
from requests.auth import HTTPBasicAuth
from PIL import Image
import re

# Set the timezone
mexico_city_tz = pytz.timezone("America/Mexico_City")

# Fetch API credentials from environment variables or fall back to default placeholders
api_key = os.getenv('API_KEY', 'your_api_key')
key_secret = os.getenv('API_SECRET', 'your_api_secret')

# Define the base URL and endpoints
base_url = "https://api.sse.cisco.com"
token_endpoint = f"{base_url}/auth/v2/token"
identity_endpoint = f"{base_url}/reports/v2/identities"
user_summaries_endpoint = f"{base_url}/admin/v2/ztna/userSummaries"
ztna_activity_endpoint = f"{base_url}/reports/v2/activity/ztna"
vpn_user_connections_endpoint = f"{base_url}/admin/v2/vpn/userConnections"
private_resources_endpoint = f"{base_url}/policies/v2/privateResources"

# Function to get the Bearer token
def get_bearer_token():
    response = requests.post(token_endpoint, auth=HTTPBasicAuth(api_key, key_secret))
    response.raise_for_status()  # Raise an error for bad status codes
    token = response.json().get('access_token')
    return token

# Function to format the timedelta as "Xd Xh Xm"
def format_timedelta(td):
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes = remainder // 60
    
    if days > 0:
        return f"{days}d {hours}h {minutes:02}m"
    elif hours > 0:
        return f"{hours}h {minutes:02}m"
    else:
        return f"{minutes}m"

# Function to extract the relevant part of the Device Name for matching
def extract_identifier(device_name):
    match = re.search(r'[A-Za-z]\d{7}', device_name)
    return match.group(0) if match else None

# Function to make a request with retries and a timeout
@st.cache_data(ttl=3600)  # Cache the API response for 1 hour
def make_request(url, headers, params=None, max_retries=5, timeout=60, delay=1):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=timeout, verify=False)
            response.raise_for_status()  # Will raise an HTTPError for bad responses
            return response
        except requests.exceptions.RequestException as e:
            st.write(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay)  # Wait before retrying
                delay *= 2  # Exponential backoff
            else:
                raise

# Function to fetch VPN user connections with correct pagination
@st.cache_data(ttl=3600)  # Cache the VPN data for 1 hour
def fetch_vpn_user_connections(headers, max_offset=10000, chunk_size=500):
    vpn_user_connections = []
    offset = 0
    total = 0

    while True:
        params = {
            'limit': chunk_size,
            'offset': offset
        }

        response = make_request(vpn_user_connections_endpoint, headers=headers, params=params)
        data = response.json().get('data', [])
        total = response.json().get('total', 0)
        
        if data:
            vpn_user_connections.extend(data)
        else:
            break  # Exit loop if no new data is returned

        if len(data) < chunk_size:
            break  # Exit loop if the last page has fewer entries than the chunk size

        offset += chunk_size  # Increase offset to get the next page of results

    return vpn_user_connections, total

# Function to fetch all private resources with correct pagination
@st.cache_data(ttl=3600)  # Cache the private resources for 1 hour
def fetch_all_private_resources(headers):
    private_resources = []
    offset = 0
    chunk_size = 100  # Adjusted to match what the server returns; can be set to the max the API allows.

    while True:
        params = {
            'limit': chunk_size,
            'offset': offset
        }

        response = make_request(private_resources_endpoint, headers=headers, params=params)
        data = response.json().get('items', [])
        total_resources = response.json().get('total', 0)

        if data:
            private_resources.extend([resource['name'] for resource in data])
        else:
            break  # Exit loop if no new data is returned

        offset += chunk_size  # Increase offset to get the next page of results

        # Exit if we've retrieved all items
        if offset >= total_resources:
            break

    return set(private_resources)  # Return as a set for easy comparison

# Function to save ZTNA data hourly to local files
def save_ztna_data_hourly(ztna_data, directory="ztna_data"):
    if not os.path.exists(directory):
        os.makedirs(directory)

    now = datetime.now(mexico_city_tz)
    file_path = os.path.join(directory, f"ztna_{now.strftime('%Y%m%d_%H')}.json")

    with open(file_path, 'w') as f:
        json.dump(ztna_data, f)

# Function to load existing ZTNA data from local files
def load_existing_ztna_data(directory="ztna_data"):
    if not os.path.exists(directory):
        return []

    all_ztna_data = []
    now = datetime.now(mexico_city_tz)
    today = now.strftime('%Y%m%d')

    for file_name in os.listdir(directory):
        if file_name.startswith(f"ztna_{today}"):
            with open(os.path.join(directory, file_name), 'r') as f:
                ztna_data = json.load(f)
                all_ztna_data.extend(ztna_data)

    return all_ztna_data

# Function to clear old ZTNA data (older than today)
def clear_old_ztna_data(directory="ztna_data"):
    if not os.path.exists(directory):
        os.makedirs(directory)  # Ensure the directory exists

    now = datetime.now(mexico_city_tz)
    today = now.strftime('%Y%m%d')

    for file_name in os.listdir(directory):
        if not file_name.startswith(f"ztna_{today}"):
            os.remove(os.path.join(directory, file_name))

# Main ZTNA fetching and processing logic with correct pagination handling
def fetch_and_process_ztna_data(headers):
    now = datetime.now(mexico_city_tz)
    today_5am = now.replace(hour=5, minute=0, second=0, microsecond=0)

    # Clear old data at the start of the day
    clear_old_ztna_data()

    # Load existing data
    existing_ztna_data = load_existing_ztna_data()

    if existing_ztna_data:
        last_entry_time = max([entry['timestamp'] for entry in existing_ztna_data]) / 1000
        from_timestamp = int(last_entry_time * 1000)
    else:
        from_timestamp = int(today_5am.timestamp() * 1000)

    to_timestamp = int(now.timestamp() * 1000)

    # Define the maximum allowable offset
    max_offset = 15000
    chunk_size = 5000
    time_chunk_size = (to_timestamp - from_timestamp) // (max_offset // chunk_size)
    new_ztna_data = []

    st.write("Processing ZTNA data...")
    while from_timestamp < to_timestamp:
        chunk_end_time = min(from_timestamp + time_chunk_size, to_timestamp)
        offset = 0

        while True:
            params = {
                'from': from_timestamp,
                'to': chunk_end_time,
                'limit': chunk_size,
                'offset': offset
            }

            try:
                ztna_response = make_request(ztna_activity_endpoint, headers=headers, params=params)
                ztna_data = ztna_response.json().get('data', [])
                new_ztna_data.extend(ztna_data)

                if not ztna_data or len(ztna_data) < chunk_size:
                    break  # No more data to fetch, exit the loop

                offset += chunk_size

                if offset >= max_offset:
                    break  # Stop if we hit the offset limit

            except requests.exceptions.HTTPError as e:
                st.write(f"Error fetching ZTNA data: {e}")
                break

        # Move the from_timestamp forward to the next chunk
        from_timestamp = chunk_end_time

    # Save new data locally
    if new_ztna_data:
        save_ztna_data_hourly(new_ztna_data)

    # Combine existing and new data
    all_ztna_data = existing_ztna_data + new_ztna_data
    return all_ztna_data

# Main script execution

# Cache bearer token using session state
if 'bearer_token' not in st.session_state:
    st.session_state['bearer_token'] = get_bearer_token()

bearer_token = st.session_state['bearer_token']

# Bearer token for authorization
headers = {
    'Authorization': f'Bearer {bearer_token}'
}

# Load images using environment variables for logo paths, with default fallbacks
@st.cache_data
def load_images():
    try:
        logo1_path = os.getenv("LOGO1_PATH", "default_logo1.png")  # Default logo if not set
        logo2_path = os.getenv("LOGO2_PATH", "default_logo2.png")  # Default logo if not set
        logo1 = Image.open(logo1_path)
        logo2 = Image.open(logo2_path)
        return logo1, logo2
    except Exception as e:
        st.error(f"Error loading images: {e}")
        return None, None

logo1, logo2 = load_images()

# Add header with logos if images are loaded
if logo1 and logo2:
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        st.image(logo1, use_column_width=True)

    with col3:
        st.image(logo2, use_column_width=True)

# Add an author header in the upper right corner
st.markdown(
    "<div style='text-align: right; font-size: 12px;'>Created by Tavo Medina</div>", 
    unsafe_allow_html=True
)

# Fetch all identities (considered as AD identities)
@st.cache_data(ttl=3600)  # Cache identities for 1 hour
def fetch_identities(headers):
    params = {
        'limit': 2000,
        'offset': 0,
        'identitytypes': 'directory_user'
    }
    response = make_request(identity_endpoint, headers=headers, params=params)
    return response.json().get('data', [])

identities = fetch_identities(headers)
st.write(f"Total Identities Fetched: {len(identities)}")

# Prepare lists to collect the data
user_details = []
users_with_active_devices = 0
users_not_enrolled = []

# Process user details in chunks
chunk_size = 100  # Increased chunk size for better performance
st.write("Processing user details...")
progress_bar = st.progress(0)

for i in range(0, len(identities), chunk_size):
    chunk = identities[i:i + chunk_size]
    user_ids = ','.join([str(identity['id']) for identity in chunk])

    # Query details for the chunk of user IDs
    user_summary_response = make_request(f"{user_summaries_endpoint}?userIds={user_ids}", headers=headers)
    user_summaries = user_summary_response.json().get('users', [])

    summary_user_ids = {int(summary['userId']) for summary in user_summaries}

    # Check which users from the chunk are not enrolled
    for identity in chunk:
        if identity['id'] not in summary_user_ids:
            users_not_enrolled.append(identity)
        else:
            for summary in user_summaries:
                if int(summary['userId']) == identity['id']:
                    device_counts = summary['deviceCertificateCounts']
                    active_devices = device_counts['active']

                    user_details.append({
                        'Name': identity['label'],
                        'Active Devices': active_devices,
                        'Expired Devices': device_counts['expired'],
                        'Revoked Devices': device_counts['revoked']
                    })

                    if active_devices > 0:
                        users_with_active_devices += 1

    # Update progress bar (capped at 1.0)
    progress = min((i + chunk_size) / len(identities), 1.0)
    progress_bar.progress(progress)

# Ensure the progress bar is completed
progress_bar.progress(1.0)

# Convert the collected data into a DataFrame for easy reporting
df = pd.DataFrame(user_details)
df.index += 1  # Start numbering from 1

# Extract 'Usuario' and 'Correo' from 'Name'
df['Usuario'] = df['Name'].apply(lambda x: x.split(' (')[0])
df['Correo'] = df['Name'].apply(lambda x: x.split(' (')[1].replace(')', ''))

# Drop the original 'Name' column as it is no longer needed
df = df.drop(columns=['Name'])

# Calculate the percentage of users with active devices
total_users = len(identities)
percentage_with_active_devices = (users_with_active_devices / total_users) * 100 if total_users > 0 else 0
remaining_percentage = 100 - percentage_with_active_devices

# Create a mapping between the identifier (Axxxxxxx) from Correo and Usuario
identifier_to_user_map = {re.search(r'[A-Za-z]\d{7}', correo).group(0): usuario for correo, usuario in zip(df['Correo'], df['Usuario'])}

# Streamlit dashboard
st.title("Dashboard de Enrolamiento")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Total de Usuarios en Active Directory")
    st.metric(label="Total Users", value=total_users)

with col2:
    st.subheader("Usuarios Enrolados con Dispositivos Activos")
    st.metric(label="Active Devices", value=users_with_active_devices, delta=f"{percentage_with_active_devices:.2f}%")

# Enrollment Progress with detailed progress bar
st.subheader("Progreso de Enrolamiento")

# Create a custom progress bar with labels
progress_bar_text = f"""
<div style='width: 100%; background-color: lightgrey; border-radius: 4px;'>
  <div style='width: {percentage_with_active_devices}%; background-color: green; color: white; text-align: left; padding-left: 5px; border-radius: 4px 0 0 4px;'>
    {percentage_with_active_devices:.2f}% Completado
  </div>
  <div style='width: {remaining_percentage}%; background-color: yellow; color: black; text-align: right; padding-right: 5px; float: right; border-radius: 0 4px 4px 0;'>
    {remaining_percentage:.2f}% Restante
  </div>
</div>
"""
st.markdown(progress_bar_text, unsafe_allow_html=True)

st.write("---")

# Detailed Report: Detailed Enrolled Users Device Report and Total AD Users who have not Enrolled yet
col1, col2 = st.columns(2)

with col1:
    st.subheader(f"Detalle de Usuarios Enrolados ({len(df)})")
    st.dataframe(df[['Usuario', 'Correo', 'Active Devices', 'Expired Devices', 'Revoked Devices']])

with col2:
    if users_not_enrolled:
        unenrolled_users = [
            {
                'Usuario': user['label'].split(' (')[0],
                'Correo': user['label'].split(' (')[1].replace(')', '')
            } for user in users_not_enrolled
        ]
        df_no_enrollment = pd.DataFrame(unenrolled_users)
        df_no_enrollment.index += 1  # Start numbering from 1
        st.subheader(f"Usuarios de AD aún sin Enrolar ({len(df_no_enrollment)})")
        st.dataframe(df_no_enrollment)
    else:
        st.subheader("Usuarios de AD aún sin Enrolar (0)")
        st.write("Todos los usuarios se han enrolado con al menos un dispositivo activo.")

st.write("---")

# Detailed Report: Users Enrolled with More Than 1 Active Device
col1, col2 = st.columns(2)

with col1:
    st.subheader("Usuarios Enrolados en Más de 1 Dispositivo")
    df_more_than_one_active = df[df['Active Devices'] > 1]
    df_more_than_one_active.index = range(1, len(df_more_than_one_active) + 1)  # Renumber starting from 1
    if not df_more_than_one_active.empty:
        st.dataframe(df_more_than_one_active[['Usuario', 'Correo', 'Active Devices', 'Expired Devices', 'Revoked Devices']])
    else:
        st.write("No hay usuarios con más de 1 dispositivo enrolado.")

with col2:
    # Pie Chart: Distribution of Active Devices per User
    active_device_counts = df['Active Devices'].value_counts().reset_index()
    active_device_counts.columns = ['Active Devices', 'User Count']
    fig_pie = px.pie(active_device_counts, names='Active Devices', values='User Count',
                     title="Distribución de Dispositivos Activos por Usuario")
    st.plotly_chart(fig_pie)

st.write("---")

# Fetch VPN user connections
st.write("Fetching Machine Tunnel Connections from the API...")
vpn_user_connections, total_connections = fetch_vpn_user_connections(headers=headers)
st.write(f"Total Machine Tunnel Connections Fetched: {total_connections}")

# Prepare the VPN user connections data for the table
vpn_data = []
now_time = datetime.utcnow().replace(tzinfo=pytz.utc)  # Current time in UTC

for connection in vpn_user_connections:
    # Convert login time to datetime and then to Mexico City time
    login_time_utc = datetime.strptime(connection['loginTime'], '%b %d %Y %I:%M:%S %p %Z').replace(tzinfo=pytz.utc)
    login_time_mx = login_time_utc.astimezone(mexico_city_tz)
    active_time = now_time - login_time_utc
    
    # Format active time as days, hours, and minutes
    active_time_str = format_timedelta(active_time)

    # Extract the identifier from Device Name
    identifier = extract_identifier(connection['deviceName'])
    usuario = identifier_to_user_map.get(identifier, 'Unknown')

    vpn_data.append({
        'Device Name': connection['deviceName'],
        'Public IP': connection['publicIp'],
        'Assigned IP': connection.get('assignedIp', 'N/A'),
        'Login Time': login_time_mx.strftime('%Y-%m-%d %H:%M:%S'),  # Format as Mexico City time
        'Active Time': active_time_str,
        'Active Time (minutes)': active_time.total_seconds() / 60,  # Active time in minutes for sorting
        'Usuario': usuario  # Mapped Usuario
    })

# Convert the data into a DataFrame for easy reporting
df_vpn = pd.DataFrame(vpn_data)

# Sort the DataFrame by Active Time (in minutes) from more to less
df_vpn = df_vpn.sort_values(by='Active Time (minutes)', ascending=False)

# Drop the 'Active Time (minutes)' column after sorting
df_vpn = df_vpn.drop(columns=['Active Time (minutes)'])

# Reset the index to ensure numbering starts from 1
df_vpn.reset_index(drop=True, inplace=True)
df_vpn.index += 1  # Start numbering from 1

# Add a new section to display Machine Tunnel Connections with the total count in the title
st.subheader(f"Machine Tunnel Connections: {total_connections}")
st.dataframe(df_vpn)

# Fetch and process ZTNA data
ztna_data = fetch_and_process_ztna_data(headers=headers)

# Fetch all private resources
all_possible_labels = fetch_all_private_resources(headers=headers)

# Get the current time for displaying in the title
now_display_time = datetime.now(mexico_city_tz).strftime('%H:%M:%S')
day_of_month = datetime.now(mexico_city_tz).strftime('%d')
month_name = datetime.now(mexico_city_tz).strftime('%B')
full_date = datetime.now(mexico_city_tz).strftime('%Y-%m-%d')

# Process the ZTNA data as usual
if ztna_data:
    # Extract and count the Private Resource labels
    private_resource_labels = []
    for entry in ztna_data:
        for application in entry.get('allapplications', []):
            if isinstance(application, dict) and application.get('type') == 'PRIVATE':
                private_resource_labels.append(application.get('label', 'Unknown'))

    # Count the occurrences of each Private Resource
    label_counts = Counter(private_resource_labels)
    df_label_counts = pd.DataFrame(label_counts.items(), columns=['Private Resource', 'Count'])
    df_label_counts = df_label_counts.sort_values(by='Count', ascending=False)
    
    st.subheader(f"Top de Aplicaciones Privadas Accesadas de 5am del {day_of_month} de {month_name} ({full_date}) hasta {now_display_time} hora de CDMX")
    fig_bar = px.bar(df_label_counts, x='Private Resource', y='Count',
                     title=f"Top de Aplicaciones Privadas Accesadas de 5am del {day_of_month} de {month_name} ({full_date}) hasta {now_display_time} hora de CDMX", labels={'Count': 'Activity Count'})
    st.plotly_chart(fig_bar)

    # Find and display private resources with no activity
    active_labels = set(df_label_counts['Private Resource'])
    inactive_labels = list(all_possible_labels - active_labels)
    
    if inactive_labels:
        st.subheader(f"Aplicaciones Privadas sin Peticiones de 5am del {day_of_month} de {month_name} ({full_date}) hasta {now_display_time} hora de CDMX")
        df_inactive = pd.DataFrame(inactive_labels, columns=['Private Resource'])
        st.dataframe(df_inactive)
    else:
        st.write("All Private Resources have activity.")
    
else:
    st.write(f"No ZTNA entries found from 5 AM until {now_display_time} in Mexico City.")