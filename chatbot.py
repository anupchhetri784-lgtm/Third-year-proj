import os
import json
import random
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline
from db import get_db_connection
from web_search import search_web
from dotenv import load_dotenv

load_dotenv()

class TravelChatbot:
    def __init__(self, intents_path="static/data/chatbot_intents.json"):
        self.intents_path = intents_path
        self.model = None
        self.responses = {}
        self.load_and_train()

    def load_and_train(self):
        try:
            if not os.path.exists(self.intents_path):
                print(f"Error: {self.intents_path} not found.")
                return

            with open(self.intents_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            X = []
            y = []

            for item in data['intents']:
                intent = item['intent']
                self.responses[intent] = item['responses']
                for pattern in item['patterns']:
                    X.append(pattern.lower())
                    y.append(intent)

            self.model = make_pipeline(
                TfidfVectorizer(ngram_range=(1, 2), stop_words='english'),
                MultinomialNB(alpha=0.1)
            )
            self.model.fit(X, y)
            print("Chatbot NLP Model trained successfully!")
        except Exception as e:
            print(f"Error training chatbot: {e}")

    def predict_intent(self, text):
        if self.model is None:
            return "greeting"
        probs = self.model.predict_proba([text.lower()])[0]
        max_idx = np.argmax(probs)
        confidence = probs[max_idx]
        predicted_intent = self.model.classes_[max_idx]

        if confidence < 0.25:
            lower_text = text.lower()
            if any(k in lower_text for k in ["trek", "hike", "mountain", "safari", "lake", "bungee", "rafting", "temple", "suggest", "recommend"]):
                return "recommendation"
            if any(k in lower_text for k in ["price", "cost", "budget", "cheap", "expensive", "under", "affordable"]):
                return "pricing"
            if any(k in lower_text for k in ["book", "reserve", "booking", "status", "my trip"]):
                return "booking_help"
            return "faq"

        return predicted_intent

    def get_response(self, user_query, user_id=None):
        lower_query = user_query.lower().replace("bardiya", "bardia")

        # ─── 0. EXPLICIT WEB SEARCH CHECK ─────────────────────────────────────
        search_prefix_match = re.match(r'^(?:search the web for|search for|google|web search|look up)\s+(.+)$', lower_query, re.IGNORECASE)
        if search_prefix_match:
            search_query = user_query[search_prefix_match.start(1):].strip()
            
            gemini_resp = self._get_gemini_response(search_query)
            if gemini_resp:
                response_text = f"&#10024; <strong>AI Travel Assistant:</strong><br><br>{gemini_resp}"
                return self._format_return(response_text, "ai_response", [])
                
            results = search_web(search_query)
            response_text = self._format_web_results(search_query, results)
            return self._format_return(response_text, "web_search", [])

        # ─── 0.5. CONVERSATIONAL QUESTION BYPASS ──────────────────────────────
        # If the user is asking a conversational question, let Gemini handle it instead of forcing a booking card.
        question_pattern = r'\b(pack|packing|weather|how|why|when|what|safe|hard|difficult|permit|gear|clothes|itinerary|plan|suggest|recommend|need|should|can i|do i|is there)\b'
        if re.search(question_pattern, lower_query):
            gemini_resp = self._get_gemini_response(user_query)
            if gemini_resp:
                return self._format_return(f"&#10024; <strong>AI Travel Assistant:</strong><br><br>{gemini_resp}", "ai_response", [])

        conn = get_db_connection()
        cursor = conn.cursor()

        # ─── 1. DYNAMIC ENTITY RECOGNITION ───────────────────────────────────
        # Check packages first (more specific match)
        cursor.execute("""
            SELECT p.*, d.name AS dest_name, d.category AS dest_category, d.location AS dest_location
            FROM packages p JOIN destinations d ON p.destination_id = d.id
        """)
        all_packages = cursor.fetchall()

        for p in all_packages:
            title_words = [w.lower() for w in p['title'].split() if len(w) > 3]
            match_count = sum(1 for w in title_words if w in lower_query)
            if match_count >= 2 or p['title'].lower() in lower_query:
                response_text = (
                    f"Great choice! Here's everything about the <strong>{p['title']}</strong>:<br><br>"
                    f"&#128205; <strong>Destination:</strong> {p['dest_name']}, {p['dest_location']}<br>"
                    f"&#127981; <strong>Category:</strong> {p['dest_category']}<br>"
                    f"&#128196; <strong>Description:</strong> {p['description']}<br>"
                    f"&#9200; <strong>Duration:</strong> {p['duration_days']} Days<br>"
                    f"&#128176; <strong>Price:</strong> Rs. {float(p['price']):,.0f}<br>"
                    f"&#128101; <strong>Group Size:</strong> Up to {p.get('group_size', 12)} people<br><br>"
                    f"Would you like to <a href='/book/{p['id']}' class='fw-bold'>book this package</a> now?"
                )
                cursor.close()
                conn.close()
                return self._format_return(response_text, "entity_query", [p])

        # Check destinations next
        cursor.execute("SELECT * FROM destinations")
        all_destinations = cursor.fetchall()

        for d in all_destinations:
            dest_name_lower = d['name'].lower()
            # Full name match OR first significant word match
            if dest_name_lower in lower_query or any(
                word in lower_query for word in dest_name_lower.split() if len(word) > 4
            ):
                # Also fetch packages for this destination
                cursor.execute("""
                    SELECT p.*, d2.name AS dest_name, d2.category AS dest_category
                    FROM packages p JOIN destinations d2 ON p.destination_id = d2.id
                    WHERE p.destination_id = %s
                """, (d['id'],))
                dest_packages = cursor.fetchall()

                pkg_list = ""
                if dest_packages:
                    pkg_list = "<br><br><strong>&#127912; Available Packages:</strong><br>"
                for p in dest_packages:
                        pkg_id = p["id"]
                        pkg_list += f"&bull; <a href='/book/{pkg_id}' class='fw-bold'>{p['title']}</a> &mdash; Rs. {float(p['price']):,.0f} ({p['duration_days']} days)<br>"

                response_text = (
                    f"Here's your complete guide to <strong>{d['name']}</strong>:<br><br>"
                    f"&#128205; <strong>Location:</strong> {d['location']}<br>"
                    f"&#127981; <strong>Category:</strong> {d['category']}<br>"
                    f"&#128196; <strong>About:</strong> {d['description']}"
                    f"{pkg_list}<br>"
                    f"Interested? Check out our <a href='/packages' class='fw-bold'>full packages list</a> for more options!"
                )
                cursor.close()
                conn.close()
                return self._format_return(response_text, "entity_query", list(dest_packages))

        # ─── 2. INTENT-BASED RESPONSES ────────────────────────────────────────
        intent = self.predict_intent(user_query)
        response_text = ""
        packages = []

        # Use Gemini for EVERYTHING except booking_status (if API key is available)
        if intent != "booking_status":
            gemini_resp = self._get_gemini_response(user_query)
            if gemini_resp:
                response_text = f"&#10024; <strong>AI Travel Assistant:</strong><br><br>{gemini_resp}"
                cursor.close()
                conn.close()
                return self._format_return(response_text, "ai_response", [])

        if intent == "recommendation":
            category = None
            if any(k in lower_query for k in ["mountain", "trek", "trekking", "hike", "hiking", "everest", "annapurna", "high altitude"]):
                category = "Mountain"
            elif any(k in lower_query for k in ["wildlife", "safari", "jungle", "tiger", "elephant", "chitwan", "bardia"]):
                category = "Wildlife"
            elif any(k in lower_query for k in ["heritage", "temple", "culture", "cultural", "square", "monastery", "buddha", "lumbini"]):
                category = "Heritage"
            elif any(k in lower_query for k in ["lake", "boating", "pokhara", "phewa", "rara"]):
                category = "Lake"
            elif any(k in lower_query for k in ["adventure", "bungee", "rafting", "extreme", "bhotekoshi", "adrenaline"]):
                category = "Adventure"

            if category:
                cursor.execute("""
                    SELECT p.*, d.name AS dest_name, d.category AS dest_category
                    FROM packages p JOIN destinations d ON p.destination_id = d.id
                    WHERE d.category = %s LIMIT 3
                """, (category,))
                packages = cursor.fetchall()
                response_text = (
                    f"Excellent taste! &#127960; Since you're into <strong>{category}</strong> adventures, "
                    f"here are my top picks for you:"
                )
            else:
                cursor.execute("""
                    SELECT p.*, d.name AS dest_name, d.category AS dest_category
                    FROM packages p JOIN destinations d ON p.destination_id = d.id
                    ORDER BY p.price DESC LIMIT 3
                """)
                packages = cursor.fetchall()
                response_text = (
                    "Nepal is full of incredible experiences! &#127968; "
                    "Here are some of my top recommended packages across different categories:"
                )

            if not packages:
                response_text = (
                    "I couldn't find specific packages for that right now, but our "
                    "<a href='/packages' class='fw-bold'>Packages page</a> has everything listed!"
                )

        elif intent == "pricing":
            numbers = re.findall(r'\b\d[\d,]*\b', user_query)
            budget = None
            if numbers:
                budget = float(numbers[0].replace(',', ''))

            if budget:
                cursor.execute("""
                    SELECT p.*, d.name AS dest_name, d.category AS dest_category
                    FROM packages p JOIN destinations d ON p.destination_id = d.id
                    WHERE p.price <= %s ORDER BY p.price DESC LIMIT 4
                """, (budget,))
                packages = cursor.fetchall()
                if packages:
                    response_text = (
                        f"Great news! &#128176; I found <strong>{len(packages)} packages</strong> within "
                        f"your budget of <strong>Rs. {budget:,.0f}</strong>:"
                    )
                else:
                    response_text = (
                        f"Hmm, there are no packages under Rs. {budget:,.0f} right now. "
                        f"Try browsing our <a href='/packages' class='fw-bold'>Packages page</a> "
                        f"or increase your budget a little!"
                    )
            else:
                cursor.execute("""
                    SELECT p.*, d.name AS dest_name, d.category AS dest_category
                    FROM packages p JOIN destinations d ON p.destination_id = d.id
                    ORDER BY p.price ASC LIMIT 4
                """)
                packages = cursor.fetchall()
                response_text = (
                    "Here are our most <strong>budget-friendly packages</strong> &#128176;, "
                    "starting from the most affordable:"
                )

        elif intent == "booking_status":
            if user_id is None:
                response_text = (
                    "&#128274; You need to be <strong>logged in</strong> to check your bookings. "
                    "Please <a href='/login' class='fw-bold'>log in here</a> and try again!"
                )
            else:
                cursor.execute("""
                    SELECT b.id, b.status, b.booked_at, b.travel_date, p.title, p.duration_days, b.total_price
                    FROM bookings b
                    JOIN packages p ON b.package_id = p.id
                    WHERE b.user_id = %s ORDER BY b.booked_at DESC
                """, (user_id,))
                user_bookings = cursor.fetchall()

                if user_bookings:
                    response_text = f"Here are your <strong>{len(user_bookings)} booking(s)</strong>:<br><br>"
                    for b in user_bookings:
                        status_emoji = "&#9989;" if b['status'] == "Confirmed" else "&#128336;" if b['status'] == "Pending" else "&#10060;"
                        date_str = b['booked_at'].strftime('%d %b %Y') if b['booked_at'] and hasattr(b['booked_at'], 'strftime') else str(b.get('booked_at', ''))
                        travel_str = b['travel_date'].strftime('%d %b %Y') if b['travel_date'] and hasattr(b['travel_date'], 'strftime') else str(b.get('travel_date', ''))
                        response_text += (
                            f"{status_emoji} <strong>{b['title']}</strong><br>"
                            f"&nbsp;&nbsp;&nbsp;Status: <strong>{b['status']}</strong> &bull; Travel Date: {travel_str}<br><br>"
                        )
                    response_text += "Visit <a href='/my-bookings' class='fw-bold'>My Bookings</a> for full details."
                else:
                    response_text = (
                        "You don't have any bookings yet! &#128247;<br><br>"
                        "Browse our <a href='/packages' class='fw-bold'>Packages</a> and start your Nepal adventure!"
                    )

        elif intent == "weather":
            response_text = (
                "&#127988;&#127950; <strong>Best Time to Visit Nepal</strong><br><br>"
                "<strong>Spring (March &ndash; May):</strong> Perfect for trekking! Rhododendrons bloom, clear skies, warm temperatures. Ideal for Everest & Annapurna treks.<br><br>"
                "<strong>Autumn (Sept &ndash; Nov):</strong> The <em>golden season</em>! Crystal-clear mountain views, stable weather, and comfortable temperatures. The most popular time to visit.<br><br>"
                "<strong>Winter (Dec &ndash; Feb):</strong> Cold at altitude but great for lower-altitude cultural tours & wildlife safaris in Chitwan/Bardia.<br><br>"
                "<strong>Monsoon (June &ndash; Aug):</strong> Lush green scenery, fewer crowds, but heavy rain. Good for Mustang (rain shadow region).<br><br>"
                "&#128204; <em>Overall recommendation: Visit in <strong>October or April</strong> for the best overall experience!</em>"
            )

        elif intent == "booking_help":
            response_text = (
                "&#128203; <strong>How to Book a Package</strong><br><br>"
                "1. Browse our <a href='/packages' class='fw-bold'>Packages page</a><br>"
                "2. Click <strong>Book Now</strong> on any package<br>"
                "3. Fill in your travel details and group size<br>"
                "4. Choose your payment method (eSewa, bank transfer, or cash)<br>"
                "5. Confirm your booking &mdash; you'll get a confirmation ID!<br><br>"
                "&#10067; <strong>Can I cancel?</strong> Yes! You can cancel from <a href='/my-bookings' class='fw-bold'>My Bookings</a> before your trip date.<br><br>"
                "&#128222; Need help? Contact us via the <a href='/contact' class='fw-bold'>Contact page</a>."
            )

        elif intent == "goodbye":
            resps = [
                "Subha Yatra! &#9992;&#65039; Safe travels and may the Himalayas await you!",
                "Goodbye! &#127956; Feel free to return anytime you need travel advice for Nepal!",
                "Take care! &#128515; We hope to see you exploring the beautiful mountains of Nepal soon!"
            ]
            response_text = random.choice(resps)

        elif intent == "greeting":
            resps = [
                "Namaste! &#127944; Welcome to your Nepal Travel Assistant! I can help you discover destinations, find packages within your budget, check travel seasons, or look up your bookings. What would you like to explore?",
                "Hello and Namaste! &#127802; I'm your AI travel guide for Nepal. Ask me about our packages, destinations like Everest or Pokhara, or the best time to visit. How can I help?",
                "Namaste! &#128578; Ready to plan your Nepal adventure? I can recommend trekking packages, wildlife safaris, cultural tours, and more. What are you interested in?"
            ]
            response_text = random.choice(resps)

        elif intent == "faq":
            # Search the web for the user's query
            results = search_web(user_query)
            if results:
                response_text = self._format_web_results(user_query, results)
            else:
                response_text = (
                    "To travel in Nepal:<br><br>"
                    "&bull; <strong>Visa:</strong> Visa on Arrival is available for most nationalities at Kathmandu Airport.<br>"
                    "&bull; <strong>Safety:</strong> Nepal is very safe, but trekkers should hire registered guides.<br>"
                    "&bull; <strong>Packing:</strong> Bring layers, broken-in boots, and water purification tablets.<br><br>"
                    "Try searching specifically for details or asking about package pricing!"
                )

        else:
            # Smart fallback with web search first
            results = search_web(user_query)
            if results:
                response_text = self._format_web_results(user_query, results)
            else:
                # Fallback to helpful suggestions if search fails
                response_text = (
                    "I'm here to help you explore Nepal! &#127968;<br><br>"
                    "Here are some things I can assist with:<br>"
                    "&bull; <strong>Destinations</strong> &mdash; 'Tell me about Pokhara'<br>"
                    "&bull; <strong>Packages</strong> &mdash; 'What is the Everest Base Camp Trek?'<br>"
                    "&bull; <strong>Budget trips</strong> &mdash; 'Packages under Rs. 20,000'<br>"
                    "&bull; <strong>Best season</strong> &mdash; 'When is the best time to visit Nepal?'<br>"
                    "&bull; <strong>My bookings</strong> &mdash; 'Show my bookings'<br><br>"
                    "Try asking one of these!"
                )

        cursor.close()
        conn.close()
        return self._format_return(response_text, intent, packages)

    def _format_web_results(self, query, results):
        if not results:
            return (
                f"I searched the web for \"<strong>{query}</strong>\" but couldn't find any relevant results right now. &#128532;<br><br>"
                "Please check your connection or try again with different keywords!"
            )
            
        html_output = f"&#127760; <strong>Web Search Results for:</strong> <em>\"{query}\"</em><br><br>"
        html_output += "<div class='web-results-container'>"
        
        for r in results:
            html_output += (
                f"<div class='web-result-item mb-3' style='border-left: 3px solid #0d6efd; padding-left: 10px;'>"
                f"&bull; <strong><a href='{r['url']}' target='_blank' class='text-decoration-underline text-primary fw-bold'>{r['title']}</a></strong><br>"
                f"<small class='text-muted' style='font-size: 0.75rem;'><i class='bi bi-globe'></i> {r['host']}</small><br>"
                f"<span class='text-secondary' style='font-size: 0.85rem; line-height: 1.3;'>{r['snippet']}</span>"
                f"</div>"
            )
            
        html_output += "</div><hr class='my-2'>"
        html_output += (
            "<small class='text-muted'>I am also your local Nepal guide! Ask me about destinations, "
            "recommendations, pricing, or bookings anytime. &#127956;</small>"
        )
        return html_output

    def _get_gemini_response(self, user_query):
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            return None
            
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=api_key)
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=user_query,
                config=types.GenerateContentConfig(
                    system_instruction="You are an expert, friendly AI travel guide for the Nepal Travel System. "
                    "Keep your answers concise, helpful, and format them nicely in HTML (use <br>, <strong>, <ul>, <li>, and emojis). "
                    "Do NOT use markdown like **bold**, you MUST use HTML tags instead. Respond naturally to the user's query about travel in Nepal. "
                    "If the user asks to contact support, admin, or asks for a phone number/email, tell them they can reach the admin directly at anupkhanal556@gmail.com or call +977 9765572121."
                )
            )
            return response.text
        except Exception as e:
            print(f"Gemini API error: {e}")
            return None

    def _format_return(self, response_text, intent, packages):
        clean_packages = []
        for p in packages:
            clean_p = dict(p)
            if 'price' in clean_p:
                clean_p['price'] = float(clean_p['price'])
            if 'created_at' in clean_p:
                clean_p['created_at'] = str(clean_p['created_at'])
            clean_packages.append(clean_p)

        return {
            "response": response_text,
            "intent": intent,
            "packages": clean_packages
        }


# Singleton instance
chatbot_agent = TravelChatbot()
