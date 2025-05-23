document.addEventListener('DOMContentLoaded', () => {
    // --- Configuration ---
    const API_BASE_URL = window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost'
    ? "http://127.0.0.1:8000/api" // For local development
    : "/api"; // For deployed environment (Render)
    const CHAT_HISTORY_STORAGE_KEY = 'promptGenChatHistory';
    const THEME_STORAGE_KEY = 'promptGenTheme';
    const NO_SELECTION_CATEGORY_ID = "please_select";

    // --- DOM Elements ---
    // Navigation & Theme
    const navLinks = document.querySelectorAll('.nav-link[data-page]');
    const pages = document.querySelectorAll('.page');
    const themeToggleBtn = document.getElementById('themeToggleBtn');
    const body = document.body;

    // Prompt Generation Section
    const taskDescriptionInput = document.getElementById('taskDescription');
    const categorySelect = document.getElementById('category');
    const generatePromptBtn = document.getElementById('generatePromptBtn');
    const promptLoadingMessage = document.getElementById('promptLoadingMessage');
    const refinedPromptOutput = document.getElementById('refinedPromptOutput');
    const copyPromptBtn = document.getElementById('copyPromptBtn');
    const startChatWithPromptBtn = document.getElementById('startChatWithPromptBtn');
    const userModificationInstructionsInput = document.getElementById('userModificationInstructions');
    const applyChangesBtn = document.getElementById('applyChangesBtn');
    const explanationList = document.getElementById('explanationList');
    const suggestionsList = document.getElementById('suggestionsList');

    // Chat Section
    const newChatBtn = document.getElementById('newChatBtn');
    const chatHistoryDiv = document.getElementById('chatHistory');
    const chatInput = document.getElementById('chatInput');
    const sendChatBtn = document.getElementById('sendChatBtn');
    const chatLoadingIndicator = document.getElementById('chatLoadingIndicator');
    const chatForm = document.getElementById('chatForm');
    const typingIndicator = document.getElementById('chatTypingIndicator');

    // --- State Variables ---
    let conversationHistory = [];
    let currentPromptContext = {
        originalTask: '',
        originalCategoryLabel: '',
        categoryId: '',
    };
    let isPromptLoading = false;
    let isChatLoading = false;

    // --- Utility Functions ---
    function autoResizeTextarea(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = textarea.scrollHeight + 'px';
    }

    function toggleLoadingState(isLoading, loadingEl, buttonsToDisable = [], textareasToDisable = []) {
        loadingEl.classList.toggle('visible', isLoading);
        loadingEl.setAttribute('aria-hidden', !isLoading);

        buttonsToDisable.forEach(btn => {
            if (btn) {
                btn.disabled = isLoading;
                btn.setAttribute('aria-busy', isLoading);
            }
        });
        textareasToDisable.forEach(textarea => {
            if (textarea) {
                textarea.disabled = isLoading;
            }
        });
    }

    function checkAndFloatLabel(element) {
        if (element.tagName === 'SELECT') {
            if (element.value && element.value !== NO_SELECTION_CATEGORY_ID) {
                element.classList.add('not-placeholder-shown');
            } else {
                element.classList.remove('not-placeholder-shown');
            }
        } else {
            if (element.value) {
                element.classList.add('not-placeholder-shown');
            } else {
                element.classList.remove('not-placeholder-shown');
            }
        }
    }

    function renderAnalysisList(listElement, items, emptyMessage) {
        listElement.innerHTML = '';
        if (items && items.length > 0) {
            items.forEach(itemText => {
                const li = document.createElement('li');
                li.textContent = itemText;
                listElement.appendChild(li);
            });
        } else {
            const li = document.createElement('li');
            li.classList.add('empty-state');
            li.innerHTML = `<i class="fas fa-lightbulb"></i> ${emptyMessage}`;
            listElement.appendChild(li);
        }
    }

    function addChatMessage(role, text) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('chat-message', role);
        messageDiv.textContent = text;
        chatHistoryDiv.appendChild(messageDiv);
        chatHistoryDiv.scrollTop = chatHistoryDiv.scrollHeight;
    }

    function togglePromptOutputButtons(isDisabled) {
        copyPromptBtn.disabled = isDisabled;
        startChatWithPromptBtn.disabled = isDisabled;
    }

    // --- Event Handlers & Core Logic ---

    [taskDescriptionInput, userModificationInstructionsInput, chatInput, categorySelect].forEach(input => {
        checkAndFloatLabel(input);
        input.addEventListener('input', () => {
            checkAndFloatLabel(input);
            if (input.tagName === 'TEXTAREA') {
                autoResizeTextarea(input);
            }
        });
        if (input.tagName === 'SELECT') {
            input.addEventListener('change', () => checkAndFloatLabel(input));
        }
    });

    // --- Page Navigation Logic (Updated for smooth scroll and nav active state) ---
    function navigateToPage(pageId) {
        const targetSection = document.getElementById(pageId);

        if (targetSection) {
            // Smooth scroll to the target section
            targetSection.scrollIntoView({ behavior: 'smooth' });

            // Update nav link active states
            navLinks.forEach(link => {
                const linkDataPage = link.getAttribute('data-page');
                const linkHref = link.getAttribute('href');
                if ((linkDataPage && linkDataPage === pageId) || (linkHref && linkHref === `#${pageId}`)) {
                    link.classList.add('active');
                } else {
                    link.classList.remove('active');
                }
            });

            // Update URL hash (pushState avoids jump)
            if (history.pushState) {
                history.pushState(null, null, `#${pageId}`);
            }
        } else {
            console.warn(`navigateToPage: Section with ID "${pageId}" not found.`);
        }
    }

    // Attach click listeners to nav links
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const pageId = link.getAttribute('data-page') || link.getAttribute('href').substring(1);
            if (pageId) {
                navigateToPage(pageId);
            }
        });
    });

    // Global navigation function for buttons outside nav (e.g., hero section)
    window.navigateToPage = navigateToPage;

    // Handle initial page load based on URL hash or default to 'home'
    const initialPageId = window.location.hash ? window.location.hash.substring(1) : 'home';
    if (document.getElementById(initialPageId)) {
        if (window.location.hash) {
            setTimeout(() => {
                navigateToPage(initialPageId);
            }, 100);
        } else {
            navLinks.forEach(link => {
                const linkDataPage = link.getAttribute('data-page');
                if (linkDataPage === 'home') link.classList.add('active');
                else link.classList.remove('active');
            });
        }
    } else if (initialPageId === 'home') {
        navLinks.forEach(link => {
            const linkDataPage = link.getAttribute('data-page');
            if (linkDataPage === 'home') link.classList.add('active');
            else link.classList.remove('active');
        });
    }

    // Intersection Observer for active nav link on scroll
    if ('IntersectionObserver' in window) {
        const pageSections = document.querySelectorAll('.page');
        const observerOptions = {
            root: null,
            rootMargin: '0px 0px -40% 0px',
            threshold: 0.1
        };

        const observerCallback = (entries) => {
            entries.forEach(entry => {
                const pageId = entry.target.id;
                if (entry.isIntersecting) {
                    navLinks.forEach(link => {
                        const linkDataPage = link.getAttribute('data-page');
                        const linkHref = link.getAttribute('href');
                        if ((linkDataPage && linkDataPage === pageId) || (linkHref && linkHref === `#${pageId}`)) {
                            link.classList.add('active');
                        } else {
                            link.classList.remove('active');
                        }
                    });
                    // Optionally update hash when section is mostly visible
                    // if (history.pushState && entry.intersectionRatio > 0.5) {
                    //     history.pushState(null, null, `#${pageId}`);
                    // }
                }
            });
        };

        const observer = new IntersectionObserver(observerCallback, observerOptions);
        pageSections.forEach(sec => {
            if (sec) observer.observe(sec);
        });
    }

    // --- Theme Toggle Logic ---
    function loadTheme() {
        const storedTheme = localStorage.getItem(THEME_STORAGE_KEY);
        if (storedTheme) {
            body.classList.remove('light-theme', 'dark-theme');
            body.classList.add(storedTheme);
            updateThemeToggleButton(storedTheme);
        } else {
            body.classList.add('light-theme');
            updateThemeToggleButton('light-theme');
        }
    }

    function toggleTheme() {
        if (body.classList.contains('light-theme')) {
            body.classList.remove('light-theme');
            body.classList.add('dark-theme');
            localStorage.setItem(THEME_STORAGE_KEY, 'dark-theme');
            updateThemeToggleButton('dark-theme');
        } else {
            body.classList.remove('dark-theme');
            body.classList.add('light-theme');
            localStorage.setItem(THEME_STORAGE_KEY, 'light-theme');
            updateThemeToggleButton('light-theme');
        }
    }

    function updateThemeToggleButton(currentTheme) {
        const icon = themeToggleBtn.querySelector('i');
        if (currentTheme === 'dark-theme') {
            icon.classList.remove('fa-moon');
            icon.classList.add('fa-sun');
            themeToggleBtn.setAttribute('aria-label', 'Toggle light theme');
        } else {
            icon.classList.remove('fa-sun');
            icon.classList.add('fa-moon');
            themeToggleBtn.setAttribute('aria-label', 'Toggle dark theme');
        }
    }

    themeToggleBtn.addEventListener('click', toggleTheme);
    loadTheme();

    // Load categories on page load
    async function loadCategories() {
        try {
            const response = await fetch(`${API_BASE_URL}/categories`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const categories = await response.json();
            categorySelect.innerHTML = `<option value="${NO_SELECTION_CATEGORY_ID}">-- Please select a category --</option>`;
            categories.forEach(cat => {
                const option = document.createElement('option');
                option.value = cat.id;
                option.textContent = cat.label;
                categorySelect.appendChild(option);
            });
            checkAndFloatLabel(categorySelect);
        } catch (error) {
            console.error("Error fetching categories:", error);
            alert("Failed to load categories. Please check the backend server and your network connection.");
        }
    }

    // --- Prompt Generation Logic ---
    generatePromptBtn.addEventListener('click', async () => {
        const taskDescription = taskDescriptionInput.value.trim();
        const category = categorySelect.value;

        if (!taskDescription) {
            alert("Please enter a task description.");
            return;
        }
        if (category === NO_SELECTION_CATEGORY_ID) {
            alert("Please select a category for prompt generation.");
            return;
        }

        isPromptLoading = true;
        toggleLoadingState(isPromptLoading, promptLoadingMessage, [generatePromptBtn, applyChangesBtn, startChatWithPromptBtn, copyPromptBtn], [taskDescriptionInput, categorySelect, userModificationInstructionsInput]);
        refinedPromptOutput.textContent = 'Generating...';
        refinedPromptOutput.classList.add('loading');
        togglePromptOutputButtons(true);
        renderAnalysisList(explanationList, [], "Explanation of the prompt's structure and effectiveness will be shown here.");
        renderAnalysisList(suggestionsList, [], "Suggestions for further refinement or alternative approaches will be provided here.");

        try {
            const response = await fetch(`${API_BASE_URL}/generate-prompt`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task_description: taskDescription,
                    category: category
                }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(`HTTP error! status: ${response.status} - ${errorData.detail || response.statusText}`);
            }

            const data = await response.json();
            refinedPromptOutput.textContent = data.optimized_prompt;
            renderAnalysisList(explanationList, data.explanation || [], "Explanation of the prompt's structure and effectiveness will be shown here.");
            renderAnalysisList(suggestionsList, data.suggestions || [], "Suggestions for further refinement or alternative approaches will be provided here.");

            currentPromptContext = {
                originalTask: data.original_task_for_mod,
                originalCategoryLabel: data.original_category_label_for_mod,
                categoryId: data.current_category_id,
            };
            userModificationInstructionsInput.value = '';
            checkAndFloatLabel(userModificationInstructionsInput);

        } catch (error) {
            console.error("Error generating prompt:", error);
            alert("Failed to generate prompt: " + error.message);
            refinedPromptOutput.textContent = 'Error generating prompt. Please try again.';
            renderAnalysisList(explanationList, [], "Error occurred during explanation generation.");
            renderAnalysisList(suggestionsList, [], "Error occurred during suggestion generation.");
        } finally {
            isPromptLoading = false;
            toggleLoadingState(isPromptLoading, promptLoadingMessage, [generatePromptBtn, applyChangesBtn, startChatWithPromptBtn, copyPromptBtn], [taskDescriptionInput, categorySelect, userModificationInstructionsInput]);
            refinedPromptOutput.classList.remove('loading');
            togglePromptOutputButtons(!refinedPromptOutput.textContent || refinedPromptOutput.textContent.startsWith('Error') || refinedPromptOutput.textContent.includes('optimized prompt will appear'));
            copyPromptBtn.innerHTML = '<i class="fas fa-copy"></i>';
        }
    });

    // --- Apply Changes Logic ---
    applyChangesBtn.addEventListener('click', async () => {
        const userModificationInstructions = userModificationInstructionsInput.value.trim();
        const currentRefinedPrompt = refinedPromptOutput.textContent;

        if (!currentRefinedPrompt || currentRefinedPrompt.startsWith('Error') || currentRefinedPrompt.includes('optimized prompt will appear')) {
            alert("Please generate an initial prompt first before applying changes.");
            return;
        }
        if (!userModificationInstructions) {
            alert("Please enter modification instructions.");
            return;
        }

        isPromptLoading = true;
        toggleLoadingState(isPromptLoading, promptLoadingMessage, [generatePromptBtn, applyChangesBtn, startChatWithPromptBtn, copyPromptBtn], [taskDescriptionInput, categorySelect, userModificationInstructionsInput]);
        refinedPromptOutput.textContent = 'Applying changes...';
        refinedPromptOutput.classList.add('loading');
        togglePromptOutputButtons(true);
        renderAnalysisList(explanationList, [], "Explanation will be updated after changes are applied.");
        renderAnalysisList(suggestionsList, [], "Suggestions will be updated after changes are applied.");

        try {
            const response = await fetch(`${API_BASE_URL}/modify-prompt`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    current_refined_prompt: currentRefinedPrompt,
                    user_modification_instructions: userModificationInstructions,
                    original_task_for_context: currentPromptContext.originalTask,
                    original_category_label_for_context: currentPromptContext.originalCategoryLabel,
                    current_category_id: currentPromptContext.categoryId,
                }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(`HTTP error! status: ${response.status} - ${errorData.detail || response.statusText}`);
            }

            const data = await response.json();
            refinedPromptOutput.textContent = data.optimized_prompt;
            renderAnalysisList(explanationList, data.explanation || [], "Explanation of the prompt's structure and effectiveness.");
            renderAnalysisList(suggestionsList, data.suggestions || [], "Suggestions for further refinement or alternative approaches.");

            currentPromptContext = {
                originalTask: data.original_task_for_mod,
                originalCategoryLabel: data.original_category_label_for_mod,
                categoryId: data.current_category_id,
            };
            userModificationInstructionsInput.value = '';
            checkAndFloatLabel(userModificationInstructionsInput);

        } catch (error) {
            console.error("Error applying changes:", error);
            alert("Failed to apply changes: " + error.message);
            refinedPromptOutput.textContent = 'Error applying changes. Please try again.';
            renderAnalysisList(explanationList, [], "Error occurred during explanation generation.");
            renderAnalysisList(suggestionsList, [], "Error occurred during suggestion generation.");
        } finally {
            isPromptLoading = false;
            toggleLoadingState(isPromptLoading, promptLoadingMessage, [generatePromptBtn, applyChangesBtn, startChatWithPromptBtn, copyPromptBtn], [taskDescriptionInput, categorySelect, userModificationInstructionsInput]);
            refinedPromptOutput.classList.remove('loading');
            togglePromptOutputButtons(!refinedPromptOutput.textContent || refinedPromptOutput.textContent.startsWith('Error') || refinedPromptOutput.textContent.includes('optimized prompt will appear'));
            copyPromptBtn.innerHTML = '<i class="fas fa-copy"></i>';
        }
    });

    // --- Copy Prompt Logic ---
    copyPromptBtn.addEventListener('click', async () => {
        const textToCopy = refinedPromptOutput.textContent;
        if (!textToCopy || textToCopy.startsWith('Error') || textToCopy.includes('optimized prompt will appear')) {
            return;
        }
        try {
            await navigator.clipboard.writeText(textToCopy);
            copyPromptBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
            setTimeout(() => {
                copyPromptBtn.innerHTML = '<i class="fas fa-copy"></i>';
            }, 1500);
        } catch (err) {
            console.error('Failed to copy text: ', err);
            alert('Failed to copy prompt. Please copy manually (browser security might prevent clipboard access).');
        }
    });

    // --- Chatbot Logic ---
    function startNewChat(saveToHistory = true) {
        conversationHistory = [];
        chatHistoryDiv.innerHTML = '';
        chatInput.value = '';
        autoResizeTextarea(chatInput);
        checkAndFloatLabel(chatInput);

        const initialGreeting = 'Hello! How can I help you today?';
        addChatMessage('model', initialGreeting);

        if (saveToHistory) {
            conversationHistory.push({ role: 'model', parts: [{ text: initialGreeting }] });
            saveChatHistory();
        }
    }

    async function sendChatMessage(message, fromPrompt = false) {
        if (!message.trim() && !fromPrompt) {
            return;
        }

        addChatMessage('user', message);
        conversationHistory.push({ role: 'user', parts: [{ text: message }] });
        chatInput.value = '';
        autoResizeTextarea(chatInput);
        checkAndFloatLabel(chatInput);

        isChatLoading = true;
        toggleLoadingState(isChatLoading, chatLoadingIndicator, [sendChatBtn, newChatBtn, generatePromptBtn, applyChangesBtn, startChatWithPromptBtn, copyPromptBtn], [chatInput, taskDescriptionInput, categorySelect, userModificationInstructionsInput]);
        chatInput.disabled = true;

        try {
            const response = await fetch(`${API_BASE_URL}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ history: conversationHistory }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(`HTTP error! status: ${response.status} - ${errorData.detail || response.statusText}`);
            }

            const data = await response.json();
            const modelResponse = data.model_response;
            addChatMessage('model', modelResponse);
            conversationHistory.push({ role: 'model', parts: [{ text: modelResponse }] });
            saveChatHistory();

        } catch (error) {
            console.error("Error in chat:", error);
            addChatMessage('model', `Error: ${error.message}. Please check backend server and try again or start a new chat.`);
        } finally {
            isChatLoading = false;
            toggleLoadingState(isChatLoading, chatLoadingIndicator, [sendChatBtn, newChatBtn, generatePromptBtn, applyChangesBtn, startChatWithPromptBtn, copyPromptBtn], [chatInput, taskDescriptionInput, categorySelect, userModificationInstructionsInput]);
            chatInput.disabled = false;
            chatInput.focus();
        }
    }

    sendChatBtn.addEventListener('click', () => {
        sendChatMessage(chatInput.value);
    });

    chatInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendChatMessage(chatInput.value);
        }
    });

    newChatBtn.addEventListener('click', () => {
        startNewChat(true);
    });

    startChatWithPromptBtn.addEventListener('click', () => {
        const refinedPrompt = refinedPromptOutput.textContent;
        if (!refinedPrompt || refinedPrompt.startsWith('Error') || refinedPrompt.includes('optimized prompt will appear')) {
            alert("Please generate or refine a prompt first to start a chat with it.");
            return;
        }
        navigateToPage('ai-chat');
        startNewChat(false);
        setTimeout(() => sendChatMessage(refinedPrompt, true), 100);
    });

    // --- Persistence (Local Storage) ---
    function saveChatHistory() {
        try {
            localStorage.setItem(CHAT_HISTORY_STORAGE_KEY, JSON.stringify(conversationHistory));
        } catch (e) {
            console.error("Error saving chat history to localStorage:", e);
        }
    }

    function loadChatHistory() {
        try {
            const storedHistory = localStorage.getItem(CHAT_HISTORY_STORAGE_KEY);
            if (storedHistory) {
                conversationHistory = JSON.parse(storedHistory);
                chatHistoryDiv.innerHTML = '';
                conversationHistory.forEach(msg => addChatMessage(msg.role, msg.parts[0].text));
            } else {
                startNewChat(true);
            }
        } catch (e) {
            console.error("Failed to load chat history from localStorage, clearing corrupted data:", e);
            localStorage.removeItem(CHAT_HISTORY_STORAGE_KEY);
            startNewChat(true);
        }
    }

    // --- Initial Load ---
    loadCategories();
    loadChatHistory();
    togglePromptOutputButtons(!refinedPromptOutput.textContent || refinedPromptOutput.textContent.startsWith('Error') || refinedPromptOutput.textContent.includes('optimized prompt will appear'));

    // --- New Chatbot Logic ---
    function toggleTyping(show) {
        typingIndicator.classList.toggle('visible', show);
    }

    async function sendChatMessage(text) {
        if (!text.trim()) return;

        addChatMessage('user', text);
        conversationHistory.push({ role: 'user', parts: [{ text }] });
        chatInput.value = '';
        chatInput.style.height = 'auto';
        toggleTyping(true);

        try {
            const response = await fetch(`${API_BASE_URL}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ history: conversationHistory })
            });

            const data = await response.json();
            const modelReply = data.model_response;
            addChatMessage('model', modelReply);
            conversationHistory.push({ role: 'model', parts: [{ text: modelReply }] });
        } catch (err) {
            console.error('Chat error:', err);
            addChatMessage('model', `⚠️ Error: ${err.message}`);
        } finally {
            toggleTyping(false);
        }
    }

    chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        sendChatMessage(chatInput.value);
    });

    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = chatInput.scrollHeight + 'px';
    });

    newChatBtn.addEventListener('click', () => {
        chatHistory.innerHTML = '';
        conversationHistory = [];
        chatInput.value = '';
        chatInput.focus();
    });
});