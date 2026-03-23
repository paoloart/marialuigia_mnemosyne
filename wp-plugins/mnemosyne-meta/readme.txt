=== Mnemosyne Title and Meta-Description ===
Contributors: ospedalemarialuigia
Tags: yoast, seo, rest-api, meta-description, title
Requires at least: 6.0
Tested up to: 6.7
Requires PHP: 7.4
Stable tag: 1.0.0
License: GPL-2.0-or-later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Espone i campi Yoast SEO (title e meta description) nella REST API di WordPress per la lettura e scrittura programmatica.

== Description ==

Questo plugin registra i meta field `_yoast_wpseo_title` e `_yoast_wpseo_metadesc` nella REST API di WordPress, permettendo di leggerli e scriverli via endpoint standard `/wp-json/wp/v2/posts/{id}`.

**Caratteristiche:**

* Espone title e meta description di Yoast SEO nella REST API
* Funziona con tutti i post type pubblici (post, pagine, custom post types)
* Sanitizzazione automatica dell'input (strip HTML, normalizzazione spazi)
* Controllo permessi: solo utenti con `edit_post` possono scrivere
* Nessuna interfaccia admin — il plugin è trasparente e non aggiunge pagine

**Esempio di utilizzo:**

Lettura:
`GET /wp-json/wp/v2/posts/123`
→ campo `meta._yoast_wpseo_title` e `meta._yoast_wpseo_metadesc`

Scrittura:
`POST /wp-json/wp/v2/posts/123`
Body: `{"meta": {"_yoast_wpseo_metadesc": "Nuova meta description"}}`

**Requisiti:**

* WordPress 6.0+
* Yoast SEO attivo
* Autenticazione REST API (Application Password o Basic Auth)

== Installation ==

1. Carica la cartella `mnemosyne-meta` in `/wp-content/plugins/`
2. Attiva il plugin dalla pagina Plugin di WordPress
3. I campi Yoast sono ora disponibili nella REST API

== Frequently Asked Questions ==

= Questo plugin modifica il comportamento di Yoast SEO? =

No. Il plugin si limita a rendere visibili e scrivibili i campi meta che Yoast già utilizza internamente. Non modifica la logica di Yoast SEO in alcun modo.

= È sicuro esporre questi campi? =

Sì. L'accesso in scrittura è protetto dal controllo `current_user_can('edit_post')`. Solo gli utenti autenticati con permessi di modifica possono scrivere. L'input è sanitizzato tramite `wp_strip_all_tags()`.

= Posso disattivare il plugin senza perdere dati? =

Sì. Il plugin non crea né modifica dati. Disattivandolo, i campi Yoast restano nel database come prima — semplicemente non saranno più accessibili via REST API.

== Changelog ==

= 1.0.0 =
* Prima versione: registrazione `_yoast_wpseo_title` e `_yoast_wpseo_metadesc` nella REST API.
