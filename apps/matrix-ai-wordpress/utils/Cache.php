<?php
if(!defined('ABSPATH')){exit;}

class MatrixAI_Cache {
    private static $instance = null;
    private $use_transients = true;
    
    private function __construct() {
        // Check for memcached/redis
        $this->use_transients = !function_exists('wp_cache_get') || 
                                 get_transient('matrix_ai_cache_test') === false;
    }
    
    public static function getInstance() {
        if(self::$instance === null) {
            self::$instance = new self();
        }
        return self::$instance;
    }
    
    public function get($key, $default = null) {
        $cache_key = 'matrix_ai_'.$key;
        
        if($this->use_transients) {
            $value = get_transient($cache_key);
        } else {
            $value = wp_cache_get($cache_key);
        }
        
        return ($value !== false) ? $value : $default;
    }
    
    public function set($key, $value, $ttl = MATRIX_AI_CACHE_TTL) {
        $cache_key = 'matrix_ai_'.$key;
        
        if($this->use_transients) {
            set_transient($cache_key, $value, $ttl);
        } else {
            wp_cache_set($cache_key, $value, '', $ttl);
        }
        
        return true;
    }
    
    public function delete($key) {
        $cache_key = 'matrix_ai_'.$key;
        
        if($this->use_transients) {
            delete_transient($cache_key);
        } else {
            wp_cache_delete($cache_key);
        }
        
        return true;
    }
    
    public function flush() {
        global $wpdb;
        $prefix = 'matrix_ai_';
        
        if($this->use_transients) {
            $wpdb->query(
                $wpdb->prepare(
                    "DELETE FROM $wpdb->options WHERE option_name LIKE %s",
                    $wpdb->esc_like('_transient_'.$prefix).'%'
                )
            );
        }
        
        return true;
    }
}
