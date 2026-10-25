<?php
/**
 * Plugin Name: M4 Circuit Macros for Enlighter
 * Description: Adds PIC and Circuit Macros syntax highlighting to the Enlighter code block.
 * Version: 1.0.0
 * Requires at least: 6.0
 * Requires PHP: 7.4
 * License: GPL-3.0-or-later
 */

if (!defined('ABSPATH')) {
    exit;
}

function m4cm_enlighter_language($languages) {
    $languages['m4cm'] = 'M4 Circuit Macros';
    return $languages;
}
add_filter('enlighter_languages', 'm4cm_enlighter_language');
add_filter('enlighter_editor_languages', 'm4cm_enlighter_language');

function m4cm_enlighter_bundle($resource, $plugin_url = '', $version = null) {
    if ($resource === 'cache/enlighterjs.min.js') {
        return plugins_url('assets/enlighterjs.min.js', __FILE__);
    }
    return $resource;
}
add_filter('enlighter_resource_url', 'm4cm_enlighter_bundle', 10, 3);
