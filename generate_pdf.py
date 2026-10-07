from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
import io

def generate_ticket_pdf(booking):
    buffer = io.BytesIO()
    
    # Create the PDF object, using the buffer as its "file."
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Define colors
    primary_color = HexColor("#2c3e50")
    accent_color = HexColor("#e74c3c")
    text_color = HexColor("#333333")
    
    # Draw header background
    c.setFillColor(primary_color)
    c.rect(0, height - 100, width, 100, fill=1, stroke=0)
    
    # Draw Header Text
    c.setFillColor(HexColor("#ffffff"))
    c.setFont("Helvetica-Bold", 24)
    c.drawString(50, height - 60, "Nepal Travel System")
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 80, "Your Booking Ticket")
    
    # Title
    c.setFillColor(accent_color)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, height - 150, "Booking Confirmation")
    
    # Booking Details
    c.setFillColor(text_color)
    c.setFont("Helvetica", 12)
    
    y_position = height - 190
    line_height = 25
    
    details = [
        f"Booking ID: #{booking.get('id', 'N/A')}",
        f"Passenger Name: {booking.get('full_name', 'N/A')}",
        f"Email: {booking.get('email', 'N/A')}",
        f"Package: {booking.get('package_title', 'N/A')}",
    ]
    
    if booking.get('travel_date'):
        details.append(f"Travel Date: {booking.get('travel_date')}")
    if booking.get('travelers') or booking.get('num_travelers'):
        travelers = booking.get('travelers') or booking.get('num_travelers')
        details.append(f"Number of Travelers: {travelers}")
    if booking.get('total_price'):
        details.append(f"Total Price: Rs. {booking.get('total_price')}")
    
    details.append(f"Status: {booking.get('status', 'Confirmed')}")
    
    for detail in details:
        c.drawString(50, y_position, detail)
        y_position -= line_height
        
    # Draw a line
    c.setStrokeColor(HexColor("#cccccc"))
    c.line(50, y_position - 10, width - 50, y_position - 10)
    
    # Footer
    c.setFont("Helvetica-Oblique", 10)
    c.setFillColor(HexColor("#7f8c8d"))
    c.drawString(50, 50, "Thank you for choosing Nepal Travel System!")
    c.drawString(50, 35, "Please present this ticket upon arrival.")
    
    # Close the PDF object cleanly
    c.showPage()
    c.save()
    
    # Move buffer position to the beginning
    buffer.seek(0)
    return buffer
