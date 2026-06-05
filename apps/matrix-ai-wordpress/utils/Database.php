<?php
if(!defined('ABSPATH')){exit;}

class MatrixAI_Database {
    private static $instance = null;
    private $logger;
    
    private function __construct() {
        $this->logger = MatrixAI_Logger::getInstance();
    }
    
    public static function getInstance() {
        if(self::$instance === null) {
            self::$instance = new self();
        }
        return self::$instance;
    }
    
    public function logChat($user_message, $bot_response, $session_id = 'default') {
        global $wpdb;
        $table = $wpdb->prefix.'matrix_chat_logs';
        
        $result = $wpdb->insert($table, [
            'session_id' => $session_id,
            'user_message' => $user_message,
            'bot_response' => $bot_response,
            'created_at' => current_time('mysql')
        ], ['%s', '%s', '%s', '%s']);
        
        if($result === false) {
            $this->logger->error('Failed to log chat', [
                'error' => $wpdb->last_error
            ]);
        }
        
        return $result !== false;
    }
    
    public function saveLead($email, $interest = '', $coupon_code = '') {
        global $wpdb;
        $table = $wpdb->prefix.'matrix_leads';
        
        $existing = $wpdb->get_row($wpdb->prepare(
            "SELECT id FROM $table WHERE email = %s",
            $email
        ));
        
        if($existing) {
            return $existing->id;
        }
        
        $result = $wpdb->insert($table, [
            'email' => $email,
            'interest' => $interest,
            'coupon_code' => $coupon_code,
            'created_at' => current_time('mysql')
        ], ['%s', '%s', '%s', '%s']);
        
        if($result === false) {
            $this->logger->error('Failed to save lead', [
                'email' => $email,
                'error' => $wpdb->last_error
            ]);
        }
        
        return $wpdb->insert_id;
    }
    
    public function getRecentChats($limit = 50) {
        global $wpdb;
        $table = $wpdb->prefix.'matrix_chat_logs';
        
        return $wpdb->get_results($wpdb->prepare(
            "SELECT * FROM $table ORDER BY created_at DESC LIMIT %d",
            $limit
        ));
    }
    
    public function optimize() {
        global $wpdb;
        $tables = [
            $wpdb->prefix.'matrix_chat_logs',
            $wpdb->prefix.'matrix_leads'
        ];
        
        foreach($tables as $table) {
            $wpdb->query("OPTIMIZE TABLE $table");
            $this->logger->debug("Optimized table: $table");
        }
    }
    
    public function cleanup($days = 90) {
        global $wpdb;
        $table = $wpdb->prefix.'matrix_chat_logs';
        $cutoff_date = date('Y-m-d', strtotime("-$days days"));
        
        $deleted = $wpdb->query($wpdb->prepare(
            "DELETE FROM $table WHERE created_at < %s",
            $cutoff_date.' 00:00:00'
        ));
        
        $this->logger->info("Cleaned up $deleted old chat logs");
        return $deleted;
    }
}
