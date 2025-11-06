#include "service_5.h"

Service5::Service5() {}

void Service5::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service5::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
