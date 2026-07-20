<?php
/**
 * Plugin Name: AB Bank Chatbot
 * Description: Embeds the AB Bank Zambia chat assistant widget on the site. Set the backend URL under Settings > AB Bank Chatbot.
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) {
    exit;
}

define('ABZ_CHATBOT_OPTION', 'abz_chatbot_backend_url');

function abz_chatbot_settings_init() {
    register_setting('abz_chatbot', ABZ_CHATBOT_OPTION, [
        'type' => 'string',
        'sanitize_callback' => 'esc_url_raw',
        'default' => '',
    ]);

    add_settings_section(
        'abz_chatbot_section',
        'AB Bank Chatbot Settings',
        function () {
            echo '<p>Enter the chatbot backend URL (no trailing slash), e.g. '
                . '<code>https://ab-bank-chatbot-demo.onrender.com</code>. '
                . 'The backend must also list this site\'s domain in its '
                . '<code>ALLOWED_ORIGINS</code> setting, or the widget will load '
                . 'but fail to send messages (a CORS block, visible in the browser console).</p>';
        },
        'abz_chatbot'
    );

    add_settings_field(
        'abz_chatbot_backend_url_field',
        'Backend URL',
        function () {
            $value = get_option(ABZ_CHATBOT_OPTION, '');
            printf(
                '<input type="url" name="%s" value="%s" class="regular-text" placeholder="https://your-chatbot-backend.example.com" />',
                esc_attr(ABZ_CHATBOT_OPTION),
                esc_attr($value)
            );
        },
        'abz_chatbot',
        'abz_chatbot_section'
    );
}
add_action('admin_init', 'abz_chatbot_settings_init');

function abz_chatbot_add_settings_page() {
    add_options_page(
        'AB Bank Chatbot',
        'AB Bank Chatbot',
        'manage_options',
        'abz_chatbot',
        function () {
            ?>
            <div class="wrap">
                <h1>AB Bank Chatbot</h1>
                <form method="post" action="options.php">
                    <?php
                    settings_fields('abz_chatbot');
                    do_settings_sections('abz_chatbot');
                    submit_button();
                    ?>
                </form>
            </div>
            <?php
        }
    );
}
add_action('admin_menu', 'abz_chatbot_add_settings_page');

function abz_chatbot_render_widget() {
    $backend_url = trim(get_option(ABZ_CHATBOT_OPTION, ''));
    if (empty($backend_url)) {
        return;
    }
    $backend_url = untrailingslashit($backend_url);
    printf(
        '<script src="%s" data-endpoint="%s" defer></script>' . "\n",
        esc_url($backend_url . '/widget/widget.js'),
        esc_url($backend_url)
    );
}
add_action('wp_footer', 'abz_chatbot_render_widget');
