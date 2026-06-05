<?php
if(!defined('ABSPATH')){exit;}

// ==========================================
// PRODUCTION CONFIG - Matrix AI PRO v2.1.0
// ==========================================

if(!defined('MATRIX_AI_DEBUG')) {
    define('MATRIX_AI_DEBUG', WP_DEBUG);
}

if(!defined('MATRIX_AI_LOG_DIR')) {
    define('MATRIX_AI_LOG_DIR', wp_upload_dir()['basedir'].'/matrix-ai-logs');
}

if(!defined('MATRIX_AI_CACHE_TTL')) {
    define('MATRIX_AI_CACHE_TTL', 3600);
}

if(!defined('MATRIX_AI_RATE_LIMIT')) {
    define('MATRIX_AI_RATE_LIMIT', 100);
}

if(!defined('MATRIX_AI_MAX_RETRIES')) {
    define('MATRIX_AI_MAX_RETRIES', 3);
}

if(!defined('MATRIX_AI_API_TIMEOUT')) {
    define('MATRIX_AI_API_TIMEOUT', 25);
}

// Ensure log directory exists
if(!is_dir(MATRIX_AI_LOG_DIR)) {
    wp_mkdir_p(MATRIX_AI_LOG_DIR);
    file_put_contents(MATRIX_AI_LOG_DIR.'/.htaccess', 'deny from all');
}
