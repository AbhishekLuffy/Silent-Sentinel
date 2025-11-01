import geocoder

DEFAULT_LOCATION_LINK = "https://www.google.com/maps?q=12.9716,77.5946"  # Set your default location here

def get_location_link():
    """
    Fetches the user's approximate location using their IP address and returns a Google Maps link.
    Falls back to a default location if unavailable.
    """
    try:
        # Get location using IP address
        g = geocoder.ip('me')
        
        # Check if coordinates were found
        if g.ok and g.latlng:
            latitude, longitude = g.latlng
            maps_link = f"https://www.google.com/maps?q={latitude},{longitude}"
            print(f"📍 Location link: {maps_link}")
            return maps_link
        else:
            print("❌ Geolocation failed: Could not determine location from IP. Using default location.")
            return DEFAULT_LOCATION_LINK
    except Exception as e:
        print(f"❌ An error occurred during geolocation: {e}. Using default location.")
        return DEFAULT_LOCATION_LINK

if __name__ == '__main__':
    # This block allows you to test the location functionality directly
    print("Fetching location link...")
    link = get_location_link()
    print(f"Result: {link}")
