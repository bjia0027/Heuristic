#include "service_14.h"

Service14::Service14() {}

void Service14::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service14::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
