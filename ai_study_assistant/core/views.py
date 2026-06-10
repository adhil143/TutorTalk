from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.contrib import messages
from django.conf import settings
from .models import Notebook, Note, Flashcard, Quiz, ChatMessage
from functools import wraps
import fitz  # PyMuPDF
import google.generativeai as genai
import json
import jwt
import datetime
import os

# Configure Gemini
api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    try:
        env_path = os.path.join(settings.BASE_DIR, "..", ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split("=", 1)
                        if len(parts) == 2 and parts[0].strip() == "GEMINI_API_KEY":
                            api_key = parts[1].strip()
                            os.environ["GEMINI_API_KEY"] = api_key
                            break
    except Exception:
        pass

genai.configure(api_key=api_key or "")
model = genai.GenerativeModel("gemini-2.5-flash")


# ================= JWT HELPERS =================

def generate_jwt_token(user):
    payload = {
        'user_id': user.id,
        'username': user.username,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=1),
        'iat': datetime.datetime.utcnow()
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')

def decode_jwt_token(token):
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

def jwt_login_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        token = request.COOKIES.get('access_token')
        if not token:
            messages.info(request, "Please log in to access the study workspace.")
            return redirect('/')
            
        payload = decode_jwt_token(token)
        if not payload:
            messages.error(request, "Session expired. Please log in again.")
            response = redirect('/')
            response.delete_cookie('access_token')
            return response
            
        try:
            user = User.objects.get(id=payload['user_id'])
            request.user = user
        except User.DoesNotExist:
            messages.error(request, "User session invalid. Please register or log in again.")
            response = redirect('/')
            response.delete_cookie('access_token')
            return response
            
        return view_func(request, *args, **kwargs)
    return _wrapped_view

# ================= PDF IMAGE EXTRACTOR =================

def extract_pdf_images(pdf_path, media_root, note_id):
    image_urls = []
    try:
        doc = fitz.open(pdf_path)
        img_dir = os.path.join(media_root, 'note_images', str(note_id))
        os.makedirs(img_dir, exist_ok=True)
        
        img_count = 0
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                
                # Check dimensions to skip tiny spacer/bullet graphics (less than 100px)
                pix = fitz.Pixmap(doc, xref)
                if pix.width < 100 or pix.height < 100:
                    continue
                
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                img_name = f"page_{page_num+1}_img_{img_index+1}.{image_ext}"
                img_path = os.path.join(img_dir, img_name)
                
                with open(img_path, "wb") as f:
                    f.write(image_bytes)
                    
                relative_url = f"/media/note_images/{note_id}/{img_name}"
                image_urls.append(relative_url)
                img_count += 1
                
                if img_count >= 5:
                    break
            if img_count >= 5:
                break
    except Exception as e:
        print(f"Error extracting images: {str(e)}")
    return image_urls

# ================= VIEWS =================

def landing(request):
    token = request.COOKIES.get('access_token')
    if token:
        payload = decode_jwt_token(token)
        if payload:
            try:
                User.objects.get(id=payload['user_id'])
                return redirect('/app/')
            except User.DoesNotExist:
                # Clear invalid cookie for user that no longer exists (e.g. after db recreate)
                response = render(request, "core/landing.html")
                response.delete_cookie('access_token')
                return response
    return render(request, "core/landing.html")

def api_register(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
            username = data.get('username')
            password = data.get('password')
            email = data.get('email', '')

            if not username or not password:
                return JsonResponse({'status': 'error', 'message': 'Username and password are required.'}, status=400)

            if User.objects.filter(username=username).exists():
                return JsonResponse({'status': 'error', 'message': 'Username already exists.'}, status=400)

            user = User.objects.create_user(username=username, password=password, email=email)
            token = generate_jwt_token(user)
            
            response = JsonResponse({'status': 'success', 'message': 'Registration successful!'})
            # Set signed JWT in HTTPOnly secure cookie
            response.set_cookie('access_token', token, max_age=86400, httponly=True, samesite='Lax')
            return response
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

def api_login(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
            username = data.get('username')
            password = data.get('password')

            if not username or not password:
                return JsonResponse({'status': 'error', 'message': 'Username and password are required.'}, status=400)

            user = authenticate(username=username, password=password)
            if user is not None:
                token = generate_jwt_token(user)
                response = JsonResponse({'status': 'success', 'message': 'Login successful!'})
                response.set_cookie('access_token', token, max_age=86400, httponly=True, samesite='Lax')
                return response
            else:
                return JsonResponse({'status': 'error', 'message': 'Invalid username or password.'}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

def api_logout(request):
    response = redirect('/')
    response.delete_cookie('access_token')
    messages.success(request, "Successfully logged out.")
    return response

@jwt_login_required
def notebook_hub(request):
    notebooks = Notebook.objects.filter(user=request.user).order_by('-created_at')

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_notebook":
            title = request.POST.get("title")
            theme_color = request.POST.get("theme_color", "cyan")
            if title:
                notebook = Notebook.objects.create(
                    user=request.user,
                    title=title,
                    theme_color=theme_color
                )
                messages.success(request, f"Notebook '{title}' created successfully!")
                return redirect(f"/app/notebook/{notebook.id}/")
            else:
                messages.error(request, "Notebook title cannot be empty.")
                return redirect("/app/")

    return render(request, "core/notebook_hub.html", {
        "notebooks": notebooks
    })

@jwt_login_required
def delete_notebook(request, notebook_id):
    notebook = get_object_or_404(Notebook, id=notebook_id, user=request.user)
    title = notebook.title
    notebook.delete()
    messages.success(request, f"Notebook '{title}' deleted successfully!")
    return redirect('/app/')

@jwt_login_required
def notebook_workspace(request, notebook_id):
    notebook = get_object_or_404(Notebook, id=notebook_id, user=request.user)
    notes = notebook.notes.all().order_by('-uploaded_at')

    if request.method == "POST":
        action = request.POST.get("action")
        
        if action == "upload":
            uploaded_file = request.FILES.get("uploaded_file")
            if uploaded_file:
                note = Note.objects.create(
                    notebook=notebook,
                    uploaded_file=uploaded_file,
                    title=uploaded_file.name
                )
                
                try:
                    pdf = fitz.open(note.uploaded_file.path)
                    text = ""
                    for page in pdf:
                        text += page.get_text()
                    note.content = text
                    
                    response = model.generate_content(
                        "Summarize these study notes clearly for students.\n\n"
                        f"Content:\n{text}\n\n"
                        "Instructions:\n"
                        "1. Structure the summary cleanly using Markdown (use ## headers for sections, bold terms, and lists).\n"
                        "2. For any math/science formulas, write them in LaTeX syntax wrapped in $$ (e.g. $$E = mc^2$$ or $$F = ma$$).\n"
                        "3. Provide a visual diagram representing the concept using a Mermaid.js chart inside a ```mermaid block (e.g. flowchart TD or graph TD). Ensure all labels are double-quoted."
                    )
                    
                    summary_content = response.text
                    
                    image_urls = extract_pdf_images(note.uploaded_file.path, settings.MEDIA_ROOT, note.id)
                    if image_urls:
                        summary_content += "\n\n## Extracted Visuals from Source\n"
                        summary_content += "Here are the photos/diagrams extracted directly from your PDF:\n\n"
                        for idx, img_url in enumerate(image_urls):
                            summary_content += f"![Extracted Image {idx+1}]({img_url})\n\n"
                            
                    note.summary = summary_content
                    messages.success(request, f"Successfully uploaded '{note.title}' and generated rich summary!")
                except Exception as e:
                    note.summary = f"Could not generate summary: {str(e)}"
                    messages.error(request, f"Failed to parse PDF or call Gemini: {str(e)}")
                
                note.save()
                return redirect(f"/app/notebook/{notebook.id}/?note_id={note.id}")

        elif action == "generate_flashcards":
            note_id = request.POST.get("note_id")
            note = get_object_or_404(Note, id=note_id, notebook__user=request.user)
            
            if not note.flashcards.exists():
                try:
                    prompt = (
                        f"Based on the following study notes text, generate 5-8 flashcard study cards. "
                        f"Each card must have a short 'question' (or concept) and a clear 'answer' (or definition). "
                        f"Return the response as a JSON array of objects, where each object has 'question' and 'answer' keys. "
                        f"Do not include markdown code block formatting like ```json, just return raw JSON.\n\n"
                        f"Notes Text:\n{note.content[:8000]}"
                    )
                    response = model.generate_content(prompt)
                    
                    resp_text = response.text.strip()
                    if resp_text.startswith("```"):
                        lines = resp_text.splitlines()
                        if lines[0].startswith("```"):
                            lines = lines[1:]
                        if lines[-1].startswith("```"):
                            lines = lines[:-1]
                        resp_text = "\n".join(lines).strip()
                    
                    cards = json.loads(resp_text)
                    for card in cards:
                        Flashcard.objects.create(
                            note=note,
                            question=card.get("question"),
                            answer=card.get("answer")
                        )
                    messages.success(request, "Flashcards generated successfully!")
                except Exception as e:
                    messages.error(request, f"Failed to generate flashcards: {str(e)}")
            return redirect(f"/app/notebook/{notebook.id}/?note_id={note.id}#flashcards")

        elif action == "generate_quiz":
            note_id = request.POST.get("note_id")
            note = get_object_or_404(Note, id=note_id, notebook__user=request.user)
            
            if not note.quizzes.exists():
                try:
                    prompt = (
                        f"Based on the following study notes, generate exactly 5 multiple choice questions. "
                        f"Return the response as a JSON array of objects, where each object has "
                        f"'question', 'option_a', 'option_b', 'option_c', 'option_d', and 'correct_option' "
                        f"(which must be either 'A', 'B', 'C', or 'D'). Do not include markdown code block formatting like "
                        f"```json, just return raw JSON.\n\n"
                        f"Notes Text:\n{note.content[:8000]}"
                    )
                    response = model.generate_content(prompt)
                    
                    resp_text = response.text.strip()
                    if resp_text.startswith("```"):
                        lines = resp_text.splitlines()
                        if lines[0].startswith("```"):
                            lines = lines[1:]
                        if lines[-1].startswith("```"):
                            lines = lines[:-1]
                        resp_text = "\n".join(lines).strip()
                        
                    quiz_items = json.loads(resp_text)
                    for item in quiz_items:
                        Quiz.objects.create(
                            note=note,
                            question=item.get("question"),
                            option_a=item.get("option_a"),
                            option_b=item.get("option_b"),
                            option_c=item.get("option_c"),
                            option_d=item.get("option_d"),
                            correct_option=item.get("correct_option").upper()
                        )
                    messages.success(request, "Interactive quiz generated successfully!")
                except Exception as e:
                    messages.error(request, f"Failed to generate quiz: {str(e)}")
            return redirect(f"/app/notebook/{notebook.id}/?note_id={note.id}#quiz")

    selected_note = None
    note_id = request.GET.get("note_id")
    if note_id:
        try:
            selected_note = Note.objects.get(id=note_id, notebook__user=request.user)
        except Note.DoesNotExist:
            pass
    elif notes.exists():
        selected_note = notes.first()
        
    flashcards = []
    quizzes = []
    if selected_note:
        flashcards = selected_note.flashcards.all().order_by('id')
        quizzes = selected_note.quizzes.all().order_by('id')
        
    chat_messages = notebook.chat_messages.all().order_by('created_at')

    return render(request, "core/dashboard.html", {
        "notebook": notebook,
        "notes": notes,
        "selected_note": selected_note,
        "flashcards": flashcards,
        "quizzes": quizzes,
        "chat_messages": chat_messages,
    })

@jwt_login_required
def delete_source(request, note_id):
    note = get_object_or_404(Note, id=note_id, notebook__user=request.user)
    notebook_id = note.notebook.id
    title = note.title
    note.delete()
    messages.success(request, f"Source '{title}' deleted successfully!")
    return redirect(f"/app/notebook/{notebook_id}/")

@jwt_login_required
def send_chat(request):
    if request.method == "POST":
        notebook_id = request.POST.get("notebook_id")
        user_message = request.POST.get("message")
        checked_source_ids_str = request.POST.get("checked_source_ids")
        
        notebook = get_object_or_404(Notebook, id=notebook_id, user=request.user)
        
        ChatMessage.objects.create(notebook=notebook, role="user", message=user_message)
        
        if checked_source_ids_str:
            try:
                checked_ids = json.loads(checked_source_ids_str)
                notes = notebook.notes.filter(id__in=checked_ids)
            except Exception:
                notes = notebook.notes.all()
        else:
            notes = notebook.notes.all()
        
        notes_context = ""
        for idx, note in enumerate(notes):
            notes_context += f"--- Source {idx+1}: {note.title} ---\n{note.content or ''}\n\n"
            
        history = notebook.chat_messages.all().order_by('created_at')[:20]
        history_context = ""
        for msg in history:
            history_context += f"{msg.role.capitalize()}: {msg.message}\n"
            
        try:
            prompt = (
                f"You are an expert AI Study Assistant. Answer the student's question based strictly on their study notes content provided below.\n\n"
                f"Study Notes Content:\n{notes_context[:12000]}\n\n"
                f"Conversation History:\n{history_context}\n"
                f"User Question: {user_message}\n"
                f"Assistant Reply:"
            )
            response = model.generate_content(prompt)
            assistant_reply = response.text.strip()
            
            ChatMessage.objects.create(notebook=notebook, role="assistant", message=assistant_reply)
            
            return JsonResponse({
                "status": "success",
                "reply": assistant_reply
            })
        except Exception as e:
            return JsonResponse({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    return JsonResponse({"status": "error", "message": "Invalid method"}, status=400)
