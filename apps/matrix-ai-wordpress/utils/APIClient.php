<?php
if(!defined('ABSPATH')){exit;}

class MatrixAI_APIClient {
    private $api_key;
    private $logger;
    private $cache;
    private $max_retries = MATRIX_AI_MAX_RETRIES;
    private $timeout = MATRIX_AI_API_TIMEOUT;
    
    public function __construct() {
        $this->api_key = get_option('matrix_ai_key');
        $this->logger = MatrixAI_Logger::getInstance();
        $this->cache = MatrixAI_Cache::getInstance();
    }
    
    public function chat($messages, $use_cache = true) {
        if(!$this->api_key) {
            $this->logger->error('API Key not configured');
            return $this->getFallbackResponse();
        }
        
        $cache_key = 'chat_response_'.md5(json_encode($messages));
        
        if($use_cache) {
            $cached = $this->cache->get($cache_key);
            if($cached !== null) {
                $this->logger->debug('Cache hit for chat request');
                return $cached;
            }
        }
        
        return $this->makeRequest('https://api.openai.com/v1/chat/completions', [
            'model' => 'gpt-4o-mini',
            'messages' => $messages,
            'temperature' => 0.6
        ], $cache_key);
    }
    
    public function transcribe($audio_file) {
        if(!$this->api_key) {
            $this->logger->error('API Key not configured for transcription');
            return null;
        }
        
        $args = [
            'headers' => [
                'Authorization' => 'Bearer '.$this->api_key
            ],
            'body' => [
                'file' => new CURLFile($audio_file),
                'model' => 'whisper-1',
                'language' => 'he'
            ],
            'timeout' => $this->timeout
        ];
        
        return $this->executeWithRetry('https://api.openai.com/v1/audio/transcriptions', $args);
    }
    
    private function makeRequest($url, $body, $cache_key = null) {
        $args = [
            'headers' => [
                'Authorization' => 'Bearer '.$this->api_key,
                'Content-Type' => 'application/json'
            ],
            'body' => json_encode($body),
            'timeout' => $this->timeout
        ];
        
        $response = $this->executeWithRetry($url, $args);
        
        if(is_array($response) && isset($response['choices'][0]['message']['content'])) {
            $result = $response['choices'][0]['message']['content'];
            if($cache_key) {
                $this->cache->set($cache_key, $result, MATRIX_AI_CACHE_TTL);
            }
            return $result;
        }
        
        return $this->getFallbackResponse();
    }
    
    private function executeWithRetry($url, $args, $attempt = 1) {
        try {
            $response = wp_remote_post($url, $args);
            
            if(is_wp_error($response)) {
                throw new Exception($response->get_error_message());
            }
            
            $code = wp_remote_retrieve_response_code($response);
            
            if($code === 429 && $attempt < $this->max_retries) {
                sleep(pow(2, $attempt));
                return $this->executeWithRetry($url, $args, $attempt + 1);
            }
            
            if($code !== 200) {
                $this->logger->warning('API returned status '.$code, [
                    'url' => $url,
                    'attempt' => $attempt
                ]);
                
                if($attempt < $this->max_retries) {
                    sleep(1);
                    return $this->executeWithRetry($url, $args, $attempt + 1);
                }
                
                return null;
            }
            
            return json_decode(wp_remote_retrieve_body($response), true);
        } catch(Exception $e) {
            $this->logger->error('API request failed: '.$e->getMessage(), [
                'url' => $url,
                'attempt' => $attempt
            ]);
            
            if($attempt < $this->max_retries) {
                sleep(1);
                return $this->executeWithRetry($url, $args, $attempt + 1);
            }
            
            return null;
        }
    }
    
    private function getFallbackResponse() {
        return 'מצטער, קיימת בעיה במערכת. אנא נסה שוב מאוחר יותר.';
    }
}
