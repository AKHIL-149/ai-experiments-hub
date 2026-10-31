const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// Conversation ids become file names, so only the exact shape generateConversationId()
// produces is accepted. Anything else (e.g. "../../package") would let a request read,
// overwrite or delete files outside the storage directory.
const ID_PATTERN = /^conv_\d{10,16}_[0-9a-f]{8}$/;

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
   * Whether a value is a well-formed conversation id
   * @param {*} conversationId
   * @returns {boolean}
   */
  static isValidId(conversationId) {
    return typeof conversationId === 'string' && ID_PATTERN.test(conversationId);
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
   * @param {string} conversationId - Optional id to create it under (must be well-formed)
   * @returns {Object} - { conversationId, createdAt }
   */
  createConversation(userId = 'default', conversationId = null) {
    if (conversationId === null) {
      conversationId = this.generateConversationId();
    } else if (!ConversationManager.isValidId(conversationId)) {
      throw new Error('Invalid conversation id');
    }
    userId = typeof userId === 'string' && userId.trim() ? userId.trim().slice(0, 64) : 'default';
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
    if (!ConversationManager.isValidId(conversationId)) {
      throw new Error('Invalid conversation id');
    }

    let conversation = this.getConversation(conversationId);

    if (!conversation) {
      // The client may hold an id whose file is gone (deleted elsewhere, cleaned up
      // after a week) - recreate it under the same id so the chat carries on.
      this.createConversation('default', conversationId);
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

    limit = Number.isInteger(limit) && limit > 0 ? limit : null;
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
    if (!ConversationManager.isValidId(conversationId)) {
      return null;
    }

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

      // Write to a temp file and rename, so a crash mid-write cannot leave a half-written
      // (unparseable) conversation behind
      const filePath = this.getConversationFilePath(conversationId);
      const tempPath = `${filePath}.${process.pid}.tmp`;
      fs.writeFileSync(tempPath, JSON.stringify(conversation, null, 2), 'utf8');
      fs.renameSync(tempPath, filePath);

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

      // A file that parses but is not a conversation must not be treated as one
      if (!conversation || !Array.isArray(conversation.messages) ||
          !conversation.metadata || typeof conversation.metadata !== 'object') {
        console.error(`Conversation file ${conversationId} has an unexpected shape`);
        return null;
      }

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
    if (!ConversationManager.isValidId(conversationId)) {
      return false;
    }

    try {
      // Remove from memory
      const wasLoaded = this.activeConversations.delete(conversationId);

      // Remove from disk
      const filePath = this.getConversationFilePath(conversationId);
      const onDisk = fs.existsSync(filePath);
      if (onDisk) {
        fs.unlinkSync(filePath);
      }

      if (!onDisk && !wasLoaded) {
        return false; // nothing by that id existed
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
        if (this.isConversationFile(file)) {
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

      limit = Number.isInteger(limit) && limit > 0 ? limit : 50;
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
        if (this.isConversationFile(file)) {
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
      const jsonFiles = files.filter(f => this.isConversationFile(f));

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
   * Whether a directory entry is a conversation file (not a temp file or a stray .json)
   * @param {string} fileName
   * @returns {boolean}
   */
  isConversationFile(fileName) {
    return fileName.endsWith('.json') && ConversationManager.isValidId(fileName.slice(0, -5));
  }

  /**
   * Get file path for conversation
   * @param {string} conversationId - Conversation identifier
   * @returns {string} - File path
   */
  getConversationFilePath(conversationId) {
    if (!ConversationManager.isValidId(conversationId)) {
      throw new Error('Invalid conversation id');
    }
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
