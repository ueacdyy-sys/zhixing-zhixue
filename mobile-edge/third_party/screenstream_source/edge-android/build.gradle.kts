plugins {
    alias(libs.plugins.androidLibrary)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.parcelize)
    alias(libs.plugins.kotlin.kapt)
    alias(libs.plugins.kotlin.compose)
}

kotlin {
    explicitApi()
    jvmToolchain(17)
}

android {
    namespace = "cn.zhixingzhixue.edge.android"
    compileSdk = rootProject.extra["compileSdkVersion"] as Int
    buildToolsVersion = rootProject.extra["buildToolsVersion"] as String

    defaultConfig {
        minSdk = rootProject.extra["minSdkVersion"] as Int
    }

    buildFeatures {
        compose = true
    }

    compileOptions {
        // Domain records use java.time while minSdk remains 24.  Desugaring is
        // required on every Android module that executes those records.
        isCoreLibraryDesugaringEnabled = true
    }
}

dependencies {
    coreLibraryDesugaring(libs.android.tools.desugar)
    api(dependencies.project(":learning-application"))
    implementation(dependencies.project(":common"))
    implementation(dependencies.project(":rtsp"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.room.runtime)
    implementation(libs.androidx.room.ktx)
    kapt(libs.androidx.room.compiler)
    implementation(libs.kotlinx.coroutines.android)
    testImplementation(kotlin("test"))
}

// AGP 9 compiles Kotlin unit tests into this directory but, with the legacy
// Kotlin/KAPT compatibility mode required by this project, does not add it to
// the Android Test task's discovery inputs.  Append only the missing classes
// directory; do not override the variant-managed runtime classpath.
tasks.withType<org.gradle.api.tasks.testing.Test>().configureEach {
    testClassesDirs = files(testClassesDirs, layout.buildDirectory.dir("tmp/kotlin-classes/debugUnitTest"))
}
