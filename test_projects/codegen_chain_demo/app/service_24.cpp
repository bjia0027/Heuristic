#include "service_24.h"

Service24::Service24() {}

void Service24::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service24::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
