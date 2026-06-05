<?php
/*
Plugin Name: Matrix AI Commerce PRO
Description: Advanced AI-powered customer service platform with voice, vision, and e-commerce integration.
Version: 2.1.0
Author: Ofir Gilboa
Text Domain: matrix-ai
Requires: 5.0
Requires PHP: 7.4
*/

if(!defined('ABSPATH')){exit;}

define('MATRIX_AI_VERSION', '2.1.0');
define('MATRIX_AI_DIR', plugin_dir_path(__FILE__));
define('MATRIX_AI_URL', plugin_dir_url(__FILE__));

// Load configuration
require_once MATRIX_AI_DIR.'config/config.php';

// Load utility classes
require_once MATRIX_AI_DIR.'utils/Logger.php';
require_once MATRIX_AI_DIR.'utils/Cache.php';
require_once MATRIX_AI_DIR.'utils/RateLimiter.php';
require_once MATRIX_AI_DIR.'utils/APIClient.php';
require_once MATRIX_AI_DIR.'utils/Database.php';
require_once MATRIX_AI_DIR.'utils/HealthCheck.php';

// Load admin and frontend
require_once MATRIX_AI_DIR.'admin/HealthDashboard.php';
require_once MATRIX_AI_DIR.'includes/ajax-enhanced.php';
require_once MATRIX_AI_DIR.'includes/frontend.php';

// Database setup
function matrix_ai_run_db_upgrade() {
    global $wpdb;
    $charset_collate = $wpdb->get_charset_collate();
    if(empty($charset_collate)) {
        $charset_collate = "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci";
    }
    
    require_once(ABSPATH.'wp-admin/includes/upgrade.php');
    
    // Leads table
    $table_leads = $wpdb->prefix.'matrix_leads';
    $sql_leads = "CREATE TABLE IF NOT EXISTS $table_leads(
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        email VARCHAR(255) UNIQUE NOT NULL,
        interest VARCHAR(500),
        coupon_code VARCHAR(100),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_email (email),
        INDEX idx_created_at (created_at)
    ) $charset_collate;";
    dbDelta($sql_leads);
    
    // Chat logs table
    $table_logs = $wpdb->prefix.'matrix_chat_logs';
    $sql_logs = "CREATE TABLE IF NOT EXISTS $table_logs(
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        session_id VARCHAR(100) NOT NULL,
        user_message LONGTEXT NOT NULL,
        bot_response LONGTEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_session (session_id),
        INDEX idx_created_at (created_at)
    ) $charset_collate;";
    dbDelta($sql_logs);
    
    // Ensure UTF-8
    $wpdb->query("ALTER TABLE $table_leads CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;");
    $wpdb->query("ALTER TABLE $table_logs CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;");
    
    update_option('matrix_ai_db_version', MATRIX_AI_VERSION);
    
    MatrixAI_Logger::getInstance()->info('Database upgraded to version '.MATRIX_AI_VERSION);
}

register_activation_hook(__FILE__, 'matrix_ai_run_db_upgrade');

// Check DB version on load
add_action('plugins_loaded', function() {
    if(get_option('matrix_ai_db_version') !== MATRIX_AI_VERSION) {
        matrix_ai_run_db_upgrade();
    }
    
    // Daily optimization
    if(!wp_next_scheduled('matrix_ai_daily_optimize')) {
        wp_schedule_event(time(), 'daily', 'matrix_ai_daily_optimize');
    }
});

add_action('matrix_ai_daily_optimize', function() {
    $db = MatrixAI_Database::getInstance();
    $db->optimize();
    $db->cleanup(90);
});

// Admin notice on activation
add_action('admin_notices', function() {
    if(get_transient('matrix_ai_activated')) {
        delete_transient('matrix_ai_activated');
        ?>
        <div class="notice notice-success is-dismissible">
            <p><strong>Matrix AI activated successfully!</strong> Configure your API key in Settings.</p>
        </div>
        <?php
    }
});

register_activation_hook(__FILE__, function() {
    set_transient('matrix_ai_activated', true, 5);
});
