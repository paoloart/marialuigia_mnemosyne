<?php
/**
 * Plugin Name:       Mnemosyne Title and Meta-Description
 * Plugin URI:        https://www.ospedalemarialuigia.it/
 * Description:       Espone i campi Yoast SEO (title e meta description) nella REST API di WordPress per la lettura e scrittura programmatica.
 * Version:           1.0.0
 * Requires at least: 6.0
 * Requires PHP:      7.4
 * Author:            Ospedale Maria Luigia — Mnemosyne
 * Author URI:        https://www.ospedalemarialuigia.it/
 * License:           GPL-2.0-or-later
 * License URI:       https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain:       mnemosyne-meta
 * Domain Path:       /languages
 *
 * @package Mnemosyne_Meta
 */

// Impedisci accesso diretto.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Versione del plugin.
 */
define( 'MNEMOSYNE_META_VERSION', '1.0.0' );

/**
 * Registra i meta Yoast nella REST API all'inizializzazione.
 *
 * Usa register_post_meta() con sanitize_callback e auth_callback
 * per esporre _yoast_wpseo_title e _yoast_wpseo_metadesc in modo sicuro.
 *
 * @since 1.0.0
 */
function mnemosyne_meta_register_fields() {

	$meta_fields = array(
		'_yoast_wpseo_title'    => array(
			'description' => __( 'SEO title gestito da Yoast SEO.', 'mnemosyne-meta' ),
			'maxlength'   => 600,
		),
		'_yoast_wpseo_metadesc' => array(
			'description' => __( 'Meta description gestita da Yoast SEO.', 'mnemosyne-meta' ),
			'maxlength'   => 1200,
		),
	);

	// Registra per tutti i post type pubblici.
	$post_types = get_post_types( array( 'public' => true ), 'names' );

	foreach ( $post_types as $post_type ) {
		foreach ( $meta_fields as $meta_key => $field_config ) {
			register_post_meta(
				$post_type,
				$meta_key,
				array(
					'type'              => 'string',
					'description'       => $field_config['description'],
					'single'            => true,
					'show_in_rest'      => true,
					'sanitize_callback' => 'mnemosyne_meta_sanitize_text',
					'auth_callback'     => 'mnemosyne_meta_auth_check',
				)
			);
		}
	}
}
add_action( 'init', 'mnemosyne_meta_register_fields' );

/**
 * Sanitizza il valore del meta field.
 *
 * Rimuove tag HTML, normalizza spazi e tronca a lunghezza sicura.
 *
 * @since 1.0.0
 *
 * @param string $value Valore grezzo dal client.
 * @return string Valore sanitizzato.
 */
function mnemosyne_meta_sanitize_text( $value ) {
	// Rimuovi tag HTML.
	$clean = wp_strip_all_tags( $value );

	// Normalizza spazi multipli.
	$clean = preg_replace( '/\s+/', ' ', $clean );

	// Trim.
	$clean = trim( $clean );

	// Limita lunghezza a 1200 caratteri (margine generoso).
	if ( mb_strlen( $clean ) > 1200 ) {
		$clean = mb_substr( $clean, 0, 1200 );
	}

	return $clean;
}

/**
 * Verifica che l'utente corrente abbia i permessi per modificare il post.
 *
 * @since 1.0.0
 *
 * @param bool   $allowed Se il meta è consentito.
 * @param string $meta_key La chiave del meta.
 * @param int    $post_id L'ID del post.
 * @return bool True se l'utente può modificare il post.
 */
function mnemosyne_meta_auth_check( $allowed, $meta_key, $post_id ) {
	return current_user_can( 'edit_post', $post_id );
}

/**
 * Aggiunge un link alla pagina delle impostazioni nella lista plugin.
 *
 * @since 1.0.0
 *
 * @param array $links Array dei link esistenti.
 * @return array Array aggiornato.
 */
function mnemosyne_meta_action_links( $links ) {
	$info_link = sprintf(
		'<span style="color:#86939e;">v%s — REST API: <code>meta._yoast_wpseo_title</code>, <code>meta._yoast_wpseo_metadesc</code></span>',
		MNEMOSYNE_META_VERSION
	);
	array_push( $links, $info_link );
	return $links;
}
add_filter( 'plugin_action_links_' . plugin_basename( __FILE__ ), 'mnemosyne_meta_action_links' );
