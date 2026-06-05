<?php
if(!defined('ABSPATH')){exit;}

add_action('wp_ajax_matrix_chat', 'matrix_ai_chat_handler_enhanced');
add_action('wp_ajax_nopriv_matrix_chat', 'matrix_ai_chat_handler_enhanced');

function matrix_ai_chat_handler_enhanced() {
    try {
        check_ajax_referer('matrix_ai_nonce', '_ajax_nonce');
        
        $message = sanitize_text_field($_POST['message'] ?? '');
        if(empty($message)) {
            wp_send_json_error(['message' => 'Empty message']);
        }
        
        // Rate limiting
        $ip = sanitize_text_field($_SERVER['REMOTE_ADDR'] ?? '');
        $rate_limiter = MatrixAI_RateLimiter::getInstance();
        
        if(!$rate_limiter->isAllowed($ip)) {
            wp_send_json_error([
                'message' => 'Too many requests. Please try again later.',
                'remaining' => 0
            ], 429);
        }
        
        $api_client = new MatrixAI_APIClient();
        $logger = MatrixAI_Logger::getInstance();
        $db = MatrixAI_Database::getInstance();
        $session_id = sanitize_text_field($_POST['session_id'] ?? 'default');
        
        // Build messages
        $store_name = get_option('matrix_ai_store_name', 'Our Store');
        $messages = [
            [
                'role' => 'system',
                'content' => "You are a helpful customer service representative for $store_name. Answer in Hebrew when the user speaks Hebrew."
            ],
            [
                'role' => 'user',
                'content' => $message
            ]
        ];
        
        $logger->debug('Chat request received', ['message_length' => strlen($message)]);
        
        // Get response with retry
        $response = $api_client->chat($messages);
        
        if($response === null) {
            $logger->error('Failed to get API response', ['message' => $message]);
            wp_send_json_error(['message' => 'Service temporarily unavailable']);
        }
        
        // Log interaction
        $db->logChat($message, $response, $session_id);
        
        $logger->info('Chat response sent', ['response_length' => strlen($response)]);
        
        wp_send_json_success([
            'text' => $response,
            'remaining' => $rate_limiter->getRemainingRequests($ip)
        ]);
        
    } catch(Exception $e) {
        $logger = MatrixAI_Logger::getInstance();
        $logger->error('AJAX Error: '.$e->getMessage(), ['trace' => $e->getTraceAsString()]);
        wp_send_json_error(['message' => 'An error occurred'], 500);
    }
}

add_action('wp_ajax_matrix_health', 'matrix_ai_health_check_ajax');
add_action('wp_ajax_nopriv_matrix_health', 'matrix_ai_health_check_ajax');

function matrix_ai_health_check_ajax() {
    $health = MatrixAI_HealthCheck::getInstance();
    $status = $health->check();
    wp_send_json_success($status);
}
