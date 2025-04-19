document.addEventListener('DOMContentLoaded', function() {
  // Login form validation
  const loginForm = document.getElementById('loginForm');
  if (loginForm) {
      loginForm.addEventListener('submit', function(e) {
          let isValid = true;
          
          const username = document.getElementById('username');
          const password = document.getElementById('password');
          
          // Clear previous errors
          clearLoginErrors();
          
          // Validate email
          if (!isValidEmail(username.value)) {
              e.preventDefault();
              displayLoginError(username, 'Geçerli bir email adresi girin (@live.acibadem.edu.tr)');
              isValid = false;
          }
          
          // Validate password (not empty)
          if (password.value.trim() === '') {
              e.preventDefault();
              displayLoginError(password, 'Şifre alanı boş bırakılamaz');
              isValid = false;
          }
          
          return isValid;
      });
  }
  
  // Function to display login errors inline
  function displayLoginError(inputElement, errorMessage) {
      // Add error class to input
      inputElement.classList.add('field-error');
      
      // Find the parent input-with-icon div
      const inputContainer = inputElement.closest('.input-with-icon');
      inputContainer.classList.add('input-with-error');
      
      // Check if error icon exists, if not create one
      let errorIcon = inputContainer.querySelector('.error-icon');
      if (!errorIcon) {
          errorIcon = document.createElement('i');
          errorIcon.className = 'fas fa-exclamation-circle error-icon';
          inputContainer.appendChild(errorIcon);
      }
      
      // Add or update the error message
      const inputGroup = inputContainer.closest('.input-group');
      let errorText = inputGroup.querySelector('.error-text');
      if (!errorText) {
          errorText = document.createElement('span');
          errorText.className = 'error-text';
          inputGroup.appendChild(errorText);
      }
      errorText.textContent = errorMessage;
  }
  
  // Function to clear login errors
  function clearLoginErrors() {
      const inputs = document.querySelectorAll('#loginForm input');
      inputs.forEach(input => {
          input.classList.remove('field-error');
          const container = input.closest('.input-with-icon');
          if (container) {
              container.classList.remove('input-with-error');
              const errorIcon = container.querySelector('.error-icon');
              if (errorIcon) errorIcon.remove();
          }
          
          const inputGroup = input.closest('.input-group');
          if (inputGroup) {
              const errorText = inputGroup.querySelector('.error-text');
              if (errorText) errorText.remove();
          }
      });
  }
  
  // Registration form validation
  const registerForm = document.getElementById('registerForm');
  if (registerForm) {
      const passwordInput = document.getElementById('registerPassword');
      
      // Update password strength meter on input
      if (passwordInput) {
          passwordInput.addEventListener('input', function() {
              updatePasswordStrength(this.value);
          });
      }
      
      registerForm.addEventListener('submit', function(e) {
          let isValid = true;
          
          // Clear previous error messages
          clearErrors();
          
          const fullName = document.getElementById('fullName').value;
          const email = document.getElementById('email').value;
          const password = document.getElementById('registerPassword').value;
          const confirmPassword = document.getElementById('confirmPassword').value;
          const termsCheckbox = document.getElementById('termsCheckbox');
          
          // Validate name
          if (fullName.trim().length < 2) {
              showError('nameError', 'Please enter your full name');
              isValid = false;
          }
          
          // Validate email
          if (!isValidEmail(email)) {
              showError('emailError', 'Please enter a valid email address');
              isValid = false;
          }
          
          // Validate password
          const passwordStrength = getPasswordStrength(password);
          if (passwordStrength < 2) {
              showError('passwordError', 'Password is too weak. Include uppercase, lowercase, numbers, and special characters');
              isValid = false;
          }
          
          // Validate password confirmation
          if (password !== confirmPassword) {
              showError('confirmPasswordError', 'Passwords do not match');
              isValid = false;
          }
          
          // Validate terms checkbox
          if (!termsCheckbox.checked) {
              showError('termsError', 'You must agree to the Terms of Service and Privacy Policy');
              isValid = false;
          }
          
          if (!isValid) {
              e.preventDefault();
          }
          
          return isValid;
      });
  }
  
  // Helper functions
  function isValidEmail(email) {
      const emailRegex = /^[^\s@]+@live\.acibadem\.edu\.tr$/;
      return emailRegex.test(email);
  }
  
  function showError(elementId, message) {
      const errorElement = document.getElementById(elementId);
      if (errorElement) {
          errorElement.textContent = message;
          errorElement.style.display = 'block';
          
          // Add red border to the related input
          const inputId = elementId.replace('Error', '');
          const inputElement = document.getElementById(inputId);
          if (inputElement) {
              inputElement.style.borderColor = '#ff4d4f';
          }
      }
  }
  
  function clearErrors() {
      const errorElements = document.querySelectorAll('.error-message');
      errorElements.forEach(element => {
          element.textContent = '';
          element.style.display = 'none';
      });
      
      // Reset input borders
      const inputs = document.querySelectorAll('input[type="text"], input[type="email"], input[type="password"]');
      inputs.forEach(input => {
          input.style.borderColor = '#ddd';
      });
  }
  
  function getPasswordStrength(password) {
      // 0 = very weak, 1 = weak, 2 = medium, 3 = strong, 4 = very strong
      let strength = 0;
      
      if (password.length >= 8) strength += 1;
      if (/[A-Z]/.test(password)) strength += 1;
      if (/[0-9]/.test(password)) strength += 1;
      if (/[^A-Za-z0-9]/.test(password)) strength += 1;
      
      return strength;
  }
  
  function updatePasswordStrength(password) {
      const strengthMeter = document.getElementById('strengthMeter');
      const strengthText = document.getElementById('strengthText');
      
      if (!strengthMeter || !strengthText) return;
      
      const strength = getPasswordStrength(password);
      let width = '0%';
      let color = '#eee';
      let text = 'Password strength';
      
      if (password.length > 0) {
          if (strength === 0) {
              width = '25%';
              color = '#ff4d4f'; // red
              text = 'Very weak';
          } else if (strength === 1) {
              width = '50%';
              color = '#faad14'; // orange
              text = 'Weak';
          } else if (strength === 2) {
              width = '75%';
              color = '#1890ff'; // blue
              text = 'Medium';
          } else if (strength === 3) {
              width = '90%';
              color = '#52c41a'; // green
              text = 'Strong';
          } else {
              width = '100%';
              color = '#13c2c2'; // teal
              text = 'Very strong';
          }
      }
      
      // Create or update the strength indicator
      let indicator = strengthMeter.querySelector('div');
      if (!indicator) {
          indicator = document.createElement('div');
          strengthMeter.appendChild(indicator);
      }
      
      indicator.style.width = width;
      indicator.style.height = '100%';
      indicator.style.backgroundColor = color;
      indicator.style.transition = 'width 0.3s ease';
      strengthText.textContent = text;
      strengthText.style.color = color;
  }
  
  // Add input focus effects
  const inputs = document.querySelectorAll('input[type="text"], input[type="email"], input[type="password"]');
  inputs.forEach(input => {
      input.addEventListener('focus', function() {
          this.parentElement.classList.add('input-focus');
      });
      
      input.addEventListener('blur', function() {
          this.parentElement.classList.remove('input-focus');
      });
  });
});