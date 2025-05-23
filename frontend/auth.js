const API_BASE_URL = window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost'
    ? "http://127.0.0.1:8000/api" // For local development
    : "/api"; // For deployed environment (Render)

document.addEventListener('DOMContentLoaded', () => {
  const loginForm = document.getElementById('loginForm');
  const registerForm = document.getElementById('registerForm');

  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = document.getElementById('loginEmail').value;
      const password = document.getElementById('loginPassword').value;

      try {
        const response = await fetch(`${API_BASE_URL}/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password })
        });

        const data = await response.json();
        if (response.ok && data.token) {
          localStorage.setItem('authToken', data.token);
          window.location.href = "index.html";
        } else {
          document.getElementById('loginError').textContent = data.detail || "Login failed";
        }
      } catch (err) {
        document.getElementById('loginError').textContent = "Login error. Try again.";
      }
    });
  }

  if (registerForm) {
    registerForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = document.getElementById('registerEmail').value;
      const password = document.getElementById('registerPassword').value;
      const confirm = document.getElementById('registerConfirm').value;

      if (password !== confirm) {
        document.getElementById('registerError').textContent = "Passwords do not match.";
        return;
      }

      try {
        const response = await fetch(`${API_BASE_URL}/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password })
        });

        const data = await response.json();
        if (response.ok) {
          window.location.href = "login.html";
        } else {
          document.getElementById('registerError').textContent = data.detail || "Registration failed";
        }
      } catch (err) {
        document.getElementById('registerError').textContent = "Error registering. Try again.";
      }
    });
  }
});
