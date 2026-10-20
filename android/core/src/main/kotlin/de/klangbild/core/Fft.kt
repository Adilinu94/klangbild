package de.klangbild.core

/**
 * Iterative Radix-2-FFT (N ist eine Zweierpotenz). Liefert das Betragsquadrat der
 * positiven Frequenzanteile (0 bis N/2). Wird vom Profil-Chroma und von der
 * Tonart-Schaetzung genutzt; die Fensterung erfolgt beim Aufrufer in float32.
 */
internal object Fft {

    fun leistung(rahmen: DoubleArray): DoubleArray {
        val n = rahmen.size
        require(n > 0 && n and (n - 1) == 0) { "FFT-Groesse muss eine Zweierpotenz sein: $n" }
        val re = rahmen.copyOf()
        val im = DoubleArray(n)

        var j = 0
        for (i in 1 until n) {
            var bit = n shr 1
            while (j and bit != 0) {
                j = j xor bit
                bit = bit shr 1
            }
            j = j xor bit
            if (i < j) {
                val tr = re[i]; re[i] = re[j]; re[j] = tr
                val ti = im[i]; im[i] = im[j]; im[j] = ti
            }
        }

        var laenge = 2
        while (laenge <= n) {
            val winkel = -2.0 * Math.PI / laenge
            val wr = kotlin.math.cos(winkel)
            val wi = kotlin.math.sin(winkel)
            var i = 0
            while (i < n) {
                var cr = 1.0
                var ci = 0.0
                for (k in 0 until laenge / 2) {
                    val aR = re[i + k]
                    val aI = im[i + k]
                    val bR = re[i + k + laenge / 2]
                    val bI = im[i + k + laenge / 2]
                    val vR = bR * cr - bI * ci
                    val vI = bR * ci + bI * cr
                    re[i + k] = aR + vR
                    im[i + k] = aI + vI
                    re[i + k + laenge / 2] = aR - vR
                    im[i + k + laenge / 2] = aI - vI
                    val nr = cr * wr - ci * wi
                    ci = cr * wi + ci * wr
                    cr = nr
                }
                i += laenge
            }
            laenge = laenge shl 1
        }

        return DoubleArray(n / 2 + 1) { k -> re[k] * re[k] + im[k] * im[k] }
    }
}
