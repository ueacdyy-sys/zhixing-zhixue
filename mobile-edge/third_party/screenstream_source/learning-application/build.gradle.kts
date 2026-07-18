plugins {
    alias(libs.plugins.kotlinJvm)
}

kotlin {
    explicitApi()
    jvmToolchain(17)
}

dependencies {
    api(dependencies.project(":learning-domain"))
    api(libs.kotlinx.coroutines.android)
    testImplementation(kotlin("test"))
}
