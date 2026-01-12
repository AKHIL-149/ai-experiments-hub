const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

/**
 * Conversation Manager - Handles conversation context and history
 */
class ConversationManager {
  constructor(options = {}) {
    this.storageDir = options.storageDir || path.join(__dirname, '../data/conversations');
    this.maxConversationLength = options.maxConversationLength || 50;
    this.contextWindow = options.contextWindow || 10;

    // In-memory cache of active conversations
    this.activeConversations = new Map();

    // Ensure storage directory exists
    this.initializeStorage();
  }

  /**
   * Initialize storage directory
   */
  initializeStorage() {
    if (!fs.existsSync(this.storageDir)) {
      fs.mkdirSync(this.storageDir, { recursive: true });
      console.log(`✓ Created conversations directory: ${this.storageDir}`);
    }
  }

  /**
   * Create a new conversation
   * @param {string} userId - Optional user identifier
   * @returns {Object} - { conversationId, createdAt }
   */
  createConversation(userId = 'default') {
    const conversationId = this.generateConversationId();
    const timestamp = new Date().toISOString();

    const conversation = {
      conversationId: conversationId,
      userId: userId,
      createdAt: timestamp,
      updatedAt: timestamp,
      messages: [],
      metadata: {
        messageCount: 0,
        lastActivity: timestamp
      }
    };

    // Store in memory
    this.activeConversations.set(conversationId, conversation);

    // Persist to disk
    this.saveConversation(conversationId);

    console.log(`✓ Created conversation: ${conversationId}`);

    return {
      conversationId: conversationId,
      createdAt: timestamp
    };
  }

  /**
   * Add message to conversation
   * @param {string} conversationId - Conversation identifier
   * @param {string} role - Message role ('user' or 'assistant')
   * @param {string} content - Message content
   * @param {Object} metadata - Optional metadata
   * @returns {Object} - Added message
   */
  addMessage(conversationId, role, content, metadata = {}) {
    let conversation = this.getConversation(conversationId);

    if (!conversation) {
      // Auto-create conversation if it doesn't exist
      this.createConversation();
      conversation = this.getConversation(conversationId);
    }

    const timestamp = new Date().toISOString();

    const message = {
      role: role,
      content: content,
      timestamp: timestamp,
      metadata: metadata
    };

    conversation.messages.push(message);
    conversation.updatedAt = timestamp;
    conversation.metadata.messageCount = conversation.messages.length;
    conversation.metadata.lastActivity = timestamp;

    // Trim conversation if too long
    if (conversation.messages.length > this.maxConversationLength) {
      const removed = conversation.messages.length - this.maxConversationLength;
      conversation.messages.splice(0, removed);
      console.log(`ℹ Trimmed ${removed} old messages from conversation ${conversationId}`);
    }

    // Update in memory
    this.activeConversations.set(conversationId, conversation);

    // Persist to disk
    this.saveConversation(conversationId);

    return message;
  }

  /**
   * Get conversation history
   * @param {string} conversationId - Conversation identifier
   * @param {number} limit - Max number of recent messages to return
   * @returns {Array} - Array of messages
   */
  getHistory(conversationId, limit = null) {
    const conversation = this.getConversation(conversationId);

    if (!conversation) {
      return [];
    }

    const messages = conversation.messages;

    if (limit && limit < messages.length) {
      return messages.slice(-limit);
    }

    return messages;
  }

  /**
   * Get conversation context (recent messages for AI)
   * @param {string} conversationId - Conversation identifier
   * @param {number} contextWindow - Number of recent messages to include
   * @returns {Array} - Context messages in OpenAI format
   */
  getContext(conversationId, contextWindow = null) {
    const windowSize = contextWindow || this.contextWindow;
    const history = this.getHistory(conversationId, windowSize);

    // Convert to OpenAI message format
    return history.map(msg => ({
      role: msg.role,
      content: msg.content
    }));
  }

  /**
   * Get conversation metadata
   * @param {string} conversationId - Conversation identifier
   * @returns {Object|null} - Conversation info without messages
   */
  getConversationInfo(conversationId) {
    const conversation = this.getConversation(conversationId);

    if (!conversation) {
      return null;
    }

    return {
      conversationId: conversation.conversationId,
      userId: conversation.userId,
      createdAt: conversation.createdAt,
      updatedAt: conversation.updatedAt,
      messageCount: conversation.metadata.messageCount,
      lastActivity: conversation.metadata.lastActivity
    };
  }

  /**
   * Get conversation from memory or disk
   * @param {string} conversationId - Conversation identifier
   * @returns {Object|null} - Conversation object
   */
  getConversation(conversationId) {
    // Check memory cache first
    if (this.activeConversations.has(conversationId)) {
      return this.activeConversations.get(conversationId);
    }

    // Try loading from disk
    const conversation = this.loadConversation(conversationId);
    if (conversation) {
      this.activeConversations.set(conversationId, conversation);
      return conversation;
    }

    return null;
  }

  /**
   * Save conversation to disk
   * @param {string} conversationId - Conversation identifier
   * @returns {boolean} - Success status
   */
  saveConversation(conversationId) {
    try {
      const conversation = this.activeConversations.get(conversationId);
      if (!conversation) {
        console.error(`Conversation ${conversationId} not found in memory`);
        return false;
      }

      const filePath = this.getConversationFilePath(conversationId);
      fs.writeFileSync(filePath, JSON.stringify(conversation, null, 2), 'utf8');

      return true;
    } catch (error) {
      console.error(`Failed to save conversation ${conversationId}:`, error.message);
      return false;
    }
  }

  /**
   * Load conversation from disk
   * @param {string} conversationId - Conversation identifier
   * @returns {Object|null} - Conversation object
   */
  loadConversation(conversationId) {
    try {
      const filePath = this.getConversationFilePath(conversationId);

      if (!fs.existsSync(filePath)) {
        return null;
      }

      const data = fs.readFileSync(filePath, 'utf8');
      const conversation = JSON.parse(data);

      return conversation;
    } catch (error) {
      console.error(`Failed to load conversation ${conversationId}:`, error.message);
      return null;
    }
  }

  /**
   * Delete conversation
   * @param {string} conversationId - Conversation identifier
   * @returns {boolean} - Success status
   */
  deleteConversation(conversationId) {
    try {
      // Remove from memory
      this.activeConversations.delete(conversationId);

      // Remove from disk
      const filePath = this.getConversationFilePath(conversationId);
      if (fs.existsSync(filePath)) {
        fs.unlinkSync(filePath);
      }

      console.log(`✓ Deleted conversation: ${conversationId}`);
      return true;
    } catch (error) {
      console.error(`Failed to delete conversation ${conversationId}:`, error.message);
      return false;
    }
  }

  /**
   * List all conversations
   * @param {number} limit - Max number of conversations to return
   * @returns {Array} - Array of conversation info objects
   */
  listConversations(limit = 50) {
    try {
      const files = fs.readdirSync(this.storageDir);
      const conversations = [];

      for (const file of files) {
        if (file.endsWith('.json')) {
          const conversationId = file.replace('.json', '');
          const info = this.getConversationInfo(conversationId);
          if (info) {
            conversations.push(info);
          }
        }
      }

      // Sort by last activity (most recent first)
      conversations.sort((a, b) =>
        new Date(b.lastActivity) - new Date(a.lastActivity)
      );

      return conversations.slice(0, limit);
    } catch (error) {
      console.error('Failed to list conversations:', error.message);
      return [];
    }
  }

  /**
   * Clean up old conversations
   * @param {number} maxAgeMs - Max age in milliseconds
   * @returns {number} - Number of conversations deleted
   */
  cleanupOldConversations(maxAgeMs = 7 * 24 * 60 * 60 * 1000) {
    try {
      const files = fs.readdirSync(this.storageDir);
      const now = Date.now();
      let deleted = 0;

      for (const file of files) {
        if (file.endsWith('.json')) {
          const filePath = path.join(this.storageDir, file);
          const stats = fs.statSync(filePath);
          const fileAge = now - stats.mtimeMs;

          if (fileAge > maxAgeMs) {
            const conversationId = file.replace('.json', '');
            if (this.deleteConversation(conversationId)) {
              deleted++;
            }
          }
        }
      }

      if (deleted > 0) {
        console.log(`✓ Cleaned up ${deleted} old conversation(s)`);
      }

      return deleted;
    } catch (error) {
      console.error('Failed to cleanup conversations:', error.message);
      return 0;
    }
  }

  /**
   * Get storage statistics
   * @returns {Object} - Storage stats
   */
  getStats() {
    try {
      const files = fs.readdirSync(this.storageDir);
      const jsonFiles = files.filter(f => f.endsWith('.json'));

      let totalSize = 0;
      let totalMessages = 0;

      for (const file of jsonFiles) {
        const filePath = path.join(this.storageDir, file);
        const stats = fs.statSync(filePath);
        totalSize += stats.size;

        const conversationId = file.replace('.json', '');
        const info = this.getConversationInfo(conversationId);
        if (info) {
          totalMessages += info.messageCount;
        }
      }

      return {
        conversationCount: jsonFiles.length,
        totalMessages: totalMessages,
        storageSizeMB: (totalSize / (1024 * 1024)).toFixed(2),
        activeInMemory: this.activeConversations.size
      };
    } catch (error) {
      console.error('Failed to get stats:', error.message);
      return {
        conversationCount: 0,
        totalMessages: 0,
        storageSizeMB: 0,
        activeInMemory: 0
      };
    }
  }

  /**
   * Clear conversation messages (keep metadata)
   * @param {string} conversationId - Conversation identifier
   * @returns {boolean} - Success status
   */
  clearMessages(conversationId) {
    const conversation = this.getConversation(conversationId);

    if (!conversation) {
      return false;
    }

    conversation.messages = [];
    conversation.metadata.messageCount = 0;
    conversation.updatedAt = new Date().toISOString();

    this.activeConversations.set(conversationId, conversation);
    this.saveConversation(conversationId);

    console.log(`✓ Cleared messages from conversation: ${conversationId}`);
    return true;
  }

  /**
   * Generate unique conversation ID
   * @returns {string} - Conversation ID
   */
  generateConversationId() {
    const timestamp = Date.now();
    const random = crypto.randomBytes(4).toString('hex');
    return `conv_${timestamp}_${random}`;
  }

  /**
   * Get file path for conversation
   * @param {string} conversationId - Conversation identifier
   * @returns {string} - File path
   */
  getConversationFilePath(conversationId) {
    return path.join(this.storageDir, `${conversationId}.json`);
  }

  /**
   * Unload inactive conversations from memory
   * @param {number} inactiveThresholdMs - Threshold for inactivity
   * @returns {number} - Number of conversations unloaded
   */
  unloadInactive(inactiveThresholdMs = 30 * 60 * 1000) {
    const now = Date.now();
    let unloaded = 0;

    for (const [conversationId, conversation] of this.activeConversations) {
      const lastActivity = new Date(conversation.metadata.lastActivity).getTime();
      const inactiveDuration = now - lastActivity;

      if (inactiveDuration > inactiveThresholdMs) {
        this.activeConversations.delete(conversationId);
        unloaded++;
      }
    }

    if (unloaded > 0) {
      console.log(`ℹ Unloaded ${unloaded} inactive conversation(s) from memory`);
    }

    return unloaded;
  }
}

module.exports = ConversationManager;
